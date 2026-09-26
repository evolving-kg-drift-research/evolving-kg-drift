from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import feedparser
import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'config' / 'stage_4_3.yaml'
SOURCES_PATH = ROOT / 'config' / 'sources.yaml'
SCOPE_PATH = ROOT / 'config' / 'corpus_scope.yaml'

DISCOVERED_COLUMNS = [
    'observation_id', 'discovery_run_id', 'source_id', 'url', 'final_url',
    'discovery_method', 'source_locator', 'sitemap_url', 'rss_url',
    'section_url', 'requested_archive_datetime', 'archive_uri',
    'archive_datetime', 'discovered_at_real', 'source_declared_timestamp',
    'published_at_declared', 'modified_at_declared', 'http_status',
    'category_check_status', 'publisher_section', 'breadcrumb_path',
    'is_scope_candidate', 'request_attempts', 'error', 'window_status',
    'window_basis', 'compliance_status', 'provenance_status',
    'production_eligible', 'origin_artifact',
]
ARCHIVE_COLUMNS = [
    'archive_candidate_id', 'discovery_run_id', 'source_id', 'section_url',
    'requested_archive_datetime', 'requested_url', 'archive_uri',
    'archive_datetime', 'archived_original_url', 'final_url', 'http_status',
    'content_type', 'payload_sha256', 'discovered_at_real',
    'request_attempts', 'parse_status', 'urls_found', 'error',
    'window_status', 'compliance_status', 'production_eligible',
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def load_yaml(path: Path) -> dict:
    with path.open('r', encoding='utf-8') as handle:
        return yaml.safe_load(handle) or {}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stable_id(prefix: str, payload: dict) -> str:
    value = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':'), default=str).encode('utf-8')
    return f'{prefix}_{hashlib.sha256(value).hexdigest()}'


def local_name(tag: str) -> str:
    return tag.split('}')[-1].lower()


def parse_xml_document(payload: bytes) -> tuple[str, list[dict]]:
    root = ET.fromstring(payload)
    root_type = local_name(root.tag)
    if root_type not in {'sitemapindex', 'urlset'}:
        raise ValueError(f'unsupported XML root: {root_type}')
    rows = []
    expected = 'sitemap' if root_type == 'sitemapindex' else 'url'
    for node in list(root):
        if local_name(node.tag) != expected:
            continue
        values = {local_name(child.tag): (child.text or '').strip()
                  for child in list(node)
                  if local_name(child.tag) in {'loc', 'lastmod'}
                  and (child.text or '').strip()}
        if values.get('loc'):
            rows.append(values)
    return root_type, rows


def parse_timestamp(value: object) -> pd.Timestamp | None:
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors='coerce', utc=True)
    return None if pd.isna(parsed) else parsed


def classify_window(value: object, start: pd.Timestamp, end: pd.Timestamp) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return 'unknown'
    if parsed < start:
        return 'pre_window'
    if parsed > end:
        return 'post_window'
    return 'in_window'


def build_archive_targets(start_day: date, end_day: date,
                          target_days: list[int]) -> list[date]:
    result = []
    year, month = start_day.year, start_day.month
    while (year, month) <= (end_day.year, end_day.month):
        last = calendar.monthrange(year, month)[1]
        for day in sorted(set(target_days)):
            candidate = date(year, month, min(day, last))
            if start_day <= candidate <= end_day:
                result.append(candidate)
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return result


def normalize_article_url(href: str, base_url: str,
                          pattern: re.Pattern) -> str | None:
    candidate = urljoin(base_url, href.strip())
    replay = re.search(
        r'https?://web\.archive\.org/web/\d{1,14}(?:[a-z_]+)?/(https?://.+)',
        candidate, flags=re.IGNORECASE)
    if replay:
        candidate = replay.group(1)
    parts = urlsplit(candidate)
    host = parts.netloc.lower().split(':', 1)[0]
    if host not in {'vnexpress.net', 'www.vnexpress.net'}:
        return None
    if not pattern.search(parts.path):
        return None
    return urlunsplit(('https', 'vnexpress.net', parts.path, '', ''))


def extract_section_articles(payload: bytes, base_url: str, selector: str,
                             article_pattern: re.Pattern) -> list[str]:
    soup = BeautifulSoup(payload, 'html.parser')
    urls = set()
    for container in soup.select(selector):
        for anchor in container.find_all('a', href=True):
            url = normalize_article_url(anchor['href'], base_url, article_pattern)
            if url:
                urls.add(url)
    return sorted(urls)


def parse_archive_replay_url(value: str) -> tuple[str | None, str | None]:
    match = re.search(
        r'/web/(\d{14})(?:[a-z_]+)?/(https?://.+)$',
        value, flags=re.IGNORECASE)
    if not match:
        return None, None
    stamp = datetime.strptime(match.group(1), '%Y%m%d%H%M%S').replace(
        tzinfo=timezone.utc)
    return stamp.isoformat(), match.group(2)


def select_monthly_sitemap_probes(rows: list[dict], start: pd.Timestamp,
                                  end: pd.Timestamp) -> list[dict]:
    eligible = []
    for row in rows:
        loc = row.get('loc', '')
        if 'articles-' not in loc or 'sitemap.xml' not in loc:
            continue
        parsed = parse_timestamp(row.get('lastmod'))
        if parsed is not None and start <= parsed <= end:
            eligible.append((parsed, row))
    selected = {}
    for parsed, row in eligible:
        month = parsed.strftime('%Y-%m')
        current = selected.get(month)
        if current is None or abs(parsed.day - 15) < abs(current[0].day - 15):
            selected[month] = (parsed, row)
    return [selected[key][1] for key in sorted(selected)]


def make_observation(**values) -> dict:
    row = {column: None for column in DISCOVERED_COLUMNS}
    row.update(values)
    identity = {key: row.get(key) for key in (
        'discovery_run_id', 'source_id', 'url', 'discovery_method',
        'source_locator', 'archive_uri', 'discovered_at_real')}
    row['observation_id'] = stable_id('obs', identity)
    return row


@dataclass
class FetchResult:
    payload: bytes | None
    requested_url: str
    final_url: str | None
    http_status: int | None
    content_type: str | None
    redirect_history: list[dict]
    attempts: int
    observed_at: str
    error: str | None


class SequentialFetcher:
    def __init__(self, config: dict):
        http = config['http']
        self.delay = float(http['request_delay_seconds'])
        self.max_attempts = int(http['max_attempts'])
        self.timeout = (float(http['connect_timeout_seconds']),
                        float(http['read_timeout_seconds']))
        self.last_start = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': str(http['user_agent']),
            'Accept': 'text/html,application/xml,text/xml,application/rss+xml;q=0.9,*/*;q=0.8',
            'Accept-Encoding': 'identity',
        })

    def close(self) -> None:
        self.session.close()

    def get(self, url: str, allow_redirects: bool = True) -> FetchResult:
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            pause = self.delay - (time.monotonic() - self.last_start)
            if pause > 0:
                time.sleep(pause)
            self.last_start = time.monotonic()
            try:
                response = self.session.get(
                    url, timeout=self.timeout, allow_redirects=allow_redirects)
                history = [
                    {'status': item.status_code, 'url': item.url,
                     'location': item.headers.get('Location')}
                    for item in response.history]
                return FetchResult(
                    response.content, url, response.url, response.status_code,
                    response.headers.get('Content-Type'), history, attempt,
                    utc_now(), None)
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    time.sleep(min(2 ** (attempt - 1), 8))
        return FetchResult(
            None, url, None, None, None, [], self.max_attempts, utc_now(),
            f'{type(last_error).__name__}: {last_error}')


def fetch_event(kind: str, result: FetchResult, **extra) -> dict:
    event = {
        'event_type': kind, 'requested_url': result.requested_url,
        'final_url': result.final_url, 'http_status': result.http_status,
        'content_type': result.content_type,
        'payload_bytes': len(result.payload) if result.payload is not None else None,
        'payload_sha256': sha256_bytes(result.payload) if result.payload is not None else None,
        'redirect_history': result.redirect_history,
        'request_attempts': result.attempts,
        'discovered_at_real': result.observed_at, 'error': result.error,
        **extra,
    }
    event['event_id'] = stable_id('evt', event)
    return event


def append_event(path: Path, event: dict) -> None:
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + '\n')


def run(args: argparse.Namespace) -> Path:
    config = load_yaml(CONFIG_PATH)
    scope = load_yaml(SCOPE_PATH)
    sources = load_yaml(SOURCES_PATH)
    vn = config['vnexpress']
    source_id = str(vn['source_id'])
    registry_source = sources.get('sources', {}).get(source_id)
    if not registry_source or not registry_source.get('enabled'):
        raise RuntimeError(f'{source_id} is not enabled in config/sources.yaml')
    start_date = date.fromisoformat(scope['historical_window']['start'])
    end_date = date.fromisoformat(scope['historical_window']['end'])
    start_ts = pd.Timestamp(start_date, tz='UTC')
    end_ts = (pd.Timestamp(end_date, tz='UTC') + pd.Timedelta(days=1)
              - pd.Timedelta(microseconds=1))
    output_dir = (ROOT / args.output_dir).resolve()
    if not output_dir.is_relative_to(ROOT):
        raise ValueError('output directory must remain inside repository root')
    if output_dir.exists():
        raise FileExistsError(f'Refusing to overwrite run directory: {output_dir}')
    output_dir.mkdir(parents=True)
    log_path = output_dir / 'discovery_log.jsonl'
    fetcher = SequentialFetcher(config)
    observations, archives, events = [], [], []
    diagnostics = {
        'stage_4_3_contract_version': config['stage_4_3_contract_version'],
        'discovery_run_id': args.run_id, 'source_id': source_id,
        'historical_window': {'start': str(start_date), 'end': str(end_date)},
        'collection_constraint': 'ordinary_public_http_get_no_api',
        'cdx_used': False,
    }

    def log(event: dict) -> None:
        event.setdefault('discovery_run_id', args.run_id)
        event.setdefault('source_id', source_id)
        events.append(event)
        append_event(log_path, event)

    try:
        robots = fetcher.get(vn['robots_url'])
        log(fetch_event('robots_checked', robots,
                        compliance_status='compliant_no_api'))
        sitemap_lines = []
        if robots.payload and robots.http_status == 200:
            text = robots.payload.decode('utf-8', errors='replace')
            sitemap_lines = [line.split(':', 1)[1].strip()
                             for line in text.splitlines()
                             if line.lower().startswith('sitemap:')]
        diagnostics['robots'] = {
            'status': robots.http_status, 'sitemaps': sitemap_lines,
            'configured_sitemap_listed': vn['sitemap_url'] in sitemap_lines,
            'error': robots.error,
        }

        sitemap_result = fetcher.get(vn['sitemap_url'])
        root_type, sitemap_rows, sitemap_error = None, [], None
        if sitemap_result.payload and sitemap_result.http_status == 200:
            try:
                root_type, sitemap_rows = parse_xml_document(sitemap_result.payload)
            except Exception as exc:
                sitemap_error = f'{type(exc).__name__}: {exc}'
        log(fetch_event(
            'sitemap_root_checked', sitemap_result, xml_root=root_type,
            child_count=len(sitemap_rows), parse_error=sitemap_error,
            compliance_status='compliant_no_api'))

        probes = select_monthly_sitemap_probes(sitemap_rows, start_ts, end_ts)
        probe_events = []
        article_pattern = re.compile(vn['article_path_regex'])
        for child in probes:
            result = fetcher.get(child['loc'], allow_redirects=False)
            child_root, child_rows, parse_error = None, [], None
            if result.payload and result.http_status == 200:
                try:
                    child_root, child_rows = parse_xml_document(result.payload)
                except Exception as exc:
                    parse_error = f'{type(exc).__name__}: {exc}'
            event = fetch_event(
                'sitemap_child_checked', result, sitemap_url=child['loc'],
                sitemap_lastmod=child.get('lastmod'), xml_root=child_root,
                url_count=len(child_rows) if child_root == 'urlset' else 0,
                parse_error=parse_error, compliance_status='compliant_no_api')
            log(event)
            probe_events.append(event)
            if child_root == 'urlset':
                for item in child_rows:
                    url = normalize_article_url(
                        item['loc'], 'https://vnexpress.net/', article_pattern)
                    if not url:
                        continue
                    status = classify_window(item.get('lastmod'), start_ts, end_ts)
                    row = make_observation(
                        discovery_run_id=args.run_id, source_id=source_id,
                        url=url, discovery_method='publisher_static_sitemap',
                        source_locator=child['loc'], sitemap_url=child['loc'],
                        discovered_at_real=result.observed_at,
                        source_declared_timestamp=item.get('lastmod'),
                        is_scope_candidate=True, window_status=status,
                        window_basis='source_declared_timestamp',
                        compliance_status='compliant_no_api',
                        provenance_status='complete',
                        production_eligible=status == 'in_window',
                        origin_artifact=str(log_path.relative_to(ROOT)).replace('\\', '/'))
                    observations.append(row)
                    log({'event_type': 'url_discovered', **row})
        diagnostics['sitemap'] = {
            'root_status': sitemap_result.http_status,
            'root_type': root_type, 'root_child_count': len(sitemap_rows),
            'root_parse_error': sitemap_error,
            'monthly_child_probes': len(probes),
            'child_status_counts': pd.Series([
                item.get('http_status') for item in probe_events
            ]).value_counts(dropna=False).to_dict(),
            'child_xml_success_count': sum(
                item.get('xml_root') in {'urlset', 'sitemapindex'}
                for item in probe_events),
        }

        rss_url = str(registry_source['rss'])
        rss_result = fetcher.get(rss_url)
        feed = (feedparser.parse(rss_result.payload) if rss_result.payload
                else feedparser.FeedParserDict(entries=[]))
        log(fetch_event(
            'rss_checked', rss_result, rss_url=rss_url,
            entries_found=len(feed.entries),
            parse_warning=bool(getattr(feed, 'bozo', False)),
            compliance_status='compliant_no_api'))
        rss_counts = {}
        for entry in feed.entries:
            url = normalize_article_url(
                entry.get('link', ''), rss_result.final_url or rss_url,
                article_pattern)
            if not url:
                continue
            declared = entry.get('published') or entry.get('updated')
            status = classify_window(declared, start_ts, end_ts)
            rss_counts[status] = rss_counts.get(status, 0) + 1
            row = make_observation(
                discovery_run_id=args.run_id, source_id=source_id, url=url,
                final_url=url, discovery_method='rss_current',
                source_locator=rss_url, rss_url=rss_url,
                discovered_at_real=rss_result.observed_at,
                source_declared_timestamp=declared,
                published_at_declared=entry.get('published'),
                modified_at_declared=entry.get('updated'),
                http_status=rss_result.http_status,
                is_scope_candidate=True, request_attempts=rss_result.attempts,
                error=rss_result.error, window_status=status,
                window_basis='source_declared_timestamp',
                compliance_status='compliant_no_api',
                provenance_status='complete',
                production_eligible=status == 'in_window',
                origin_artifact=str(log_path.relative_to(ROOT)).replace('\\', '/'))
            observations.append(row)
            log({'event_type': 'url_discovered', **row})
        diagnostics['rss'] = {
            'requested_url': rss_url, 'final_url': rss_result.final_url,
            'http_status': rss_result.http_status,
            'entry_count': len(feed.entries), 'accepted_count': sum(rss_counts.values()),
            'window_status_counts': rss_counts,
            'post_window_records_retained': rss_counts.get('post_window', 0),
        }

        section_checks = []
        for section_url in vn['sections']:
            result = fetcher.get(section_url)
            event = fetch_event(
                'publisher_section_checked', result,
                section_url=section_url, compliance_status='compliant_no_api')
            log(event)
            section_checks.append(event)
        diagnostics['publisher_sections'] = [
            {
                'requested_url': item['requested_url'],
                'final_url': item['final_url'],
                'http_status': item['http_status'],
                'redirect_history': item['redirect_history'],
            }
            for item in section_checks
        ]

        targets = build_archive_targets(
            start_date, end_date, list(vn['archive_target_days']))
        if args.pilot_date:
            targets = sorted({date.fromisoformat(value)
                              for value in args.pilot_date})
        archive_status_counts = {}
        capture_months = set()
        for section_url in vn['sections']:
            for target in targets:
                requested_stamp = target.strftime('%Y%m%d') + '000000'
                requested_dt = datetime.combine(
                    target, datetime.min.time(), timezone.utc).isoformat()
                requested_url = '{}/{:s}id_/{}'.format(
                    vn['archive_replay_prefix'], requested_stamp, section_url)
                result = fetcher.get(requested_url)
                actual_dt, archived_origin = parse_archive_replay_url(
                    result.final_url or '')
                status = classify_window(actual_dt, start_ts, end_ts)
                if actual_dt and status == 'in_window':
                    capture_months.add(actual_dt[:7])
                urls, parse_status, parse_error = [], 'not_parsed', None
                if result.payload and result.http_status == 200 and actual_dt:
                    try:
                        urls = extract_section_articles(
                            result.payload, result.final_url or section_url,
                            vn['article_container_selector'], article_pattern)
                        parse_status = 'ok' if urls else 'zero_articles'
                    except Exception as exc:
                        parse_status = 'parse_error'
                        parse_error = f'{type(exc).__name__}: {exc}'
                elif result.error:
                    parse_status = 'request_error'
                    parse_error = result.error
                elif not actual_dt:
                    parse_status = 'archive_uri_unparsed'
                archive_status_counts[parse_status] = (
                    archive_status_counts.get(parse_status, 0) + 1)
                event = fetch_event(
                    'archive_replay_checked', result, section_url=section_url,
                    requested_archive_datetime=requested_dt,
                    archive_datetime=actual_dt,
                    archived_original_url=archived_origin,
                    parse_status=parse_status, urls_found=len(urls),
                    parse_error=parse_error,
                    compliance_status='compliant_no_api')
                log(event)
                candidate = {
                    'discovery_run_id': args.run_id, 'source_id': source_id,
                    'section_url': section_url,
                    'requested_archive_datetime': requested_dt,
                    'requested_url': requested_url,
                    'archive_uri': result.final_url if actual_dt else None,
                    'archive_datetime': actual_dt,
                    'archived_original_url': archived_origin,
                    'final_url': result.final_url,
                    'http_status': result.http_status,
                    'content_type': result.content_type,
                    'payload_sha256': (
                        sha256_bytes(result.payload)
                        if result.payload is not None else None),
                    'discovered_at_real': result.observed_at,
                    'request_attempts': result.attempts,
                    'parse_status': parse_status, 'urls_found': len(urls),
                    'error': parse_error, 'window_status': status,
                    'compliance_status': 'compliant_no_api',
                    'production_eligible': (
                        status == 'in_window'
                        and parse_status in {'ok', 'zero_articles'}),
                }
                candidate['archive_candidate_id'] = stable_id(
                    'arc', {key: candidate.get(key) for key in (
                        'discovery_run_id', 'source_id', 'section_url',
                        'requested_url', 'archive_uri')})
                archives.append(candidate)
                for url in urls:
                    row = make_observation(
                        discovery_run_id=args.run_id, source_id=source_id,
                        url=url, final_url=url,
                        discovery_method='wayback_replay_html',
                        source_locator=section_url, section_url=section_url,
                        requested_archive_datetime=requested_dt,
                        archive_uri=result.final_url,
                        archive_datetime=actual_dt,
                        discovered_at_real=result.observed_at,
                        http_status=result.http_status,
                        category_check_status='section_container',
                        publisher_section=urlsplit(section_url).path,
                        is_scope_candidate=True,
                        request_attempts=result.attempts,
                        error=parse_error, window_status=status,
                        window_basis='archive_datetime',
                        compliance_status='compliant_no_api',
                        provenance_status='complete',
                        production_eligible=status == 'in_window',
                        origin_artifact=str(log_path.relative_to(ROOT)).replace(
                            '\\', '/'))
                    observations.append(row)
                    log({'event_type': 'url_discovered', **row})

        diagnostics['archive_replay'] = {
            'target_dates': [value.isoformat() for value in targets],
            'section_count': len(vn['sections']),
            'requests_made': len(archives),
            'parse_status_counts': archive_status_counts,
            'in_window_capture_months': sorted(capture_months),
            'in_window_capture_month_count': len(capture_months),
            'mechanism': 'ordinary GET of public Wayback replay HTML',
            'api_endpoint_used': False,
        }
        discovered_frame = pd.DataFrame(
            observations, columns=DISCOVERED_COLUMNS)
        archive_frame = pd.DataFrame(archives, columns=ARCHIVE_COLUMNS)
        if not discovered_frame.empty:
            discovered_frame = discovered_frame.sort_values(
                'observation_id', kind='stable').reset_index(drop=True)
        if not archive_frame.empty:
            archive_frame = archive_frame.sort_values(
                'archive_candidate_id', kind='stable').reset_index(drop=True)
        discovered_path = output_dir / 'discovered_urls.parquet'
        archive_path = output_dir / 'archive_candidates.parquet'
        discovered_frame.to_parquet(discovered_path, index=False)
        archive_frame.to_parquet(archive_path, index=False)
        log({
            'event_type': 'collection_completed',
            'discovered_observation_count': len(discovered_frame),
            'archive_candidate_count': len(archive_frame),
            'production_eligible_observation_count': int(
                discovered_frame['production_eligible'].fillna(False).sum()),
            'compliance_status': 'compliant_no_api',
            'discovered_at_real': utc_now(),
        })
        diagnostics['row_counts'] = {
            'discovered_observations': len(discovered_frame),
            'archive_candidates': len(archive_frame),
            'events': len(events),
            'production_eligible_observations': int(
                discovered_frame['production_eligible'].fillna(False).sum()),
        }
        diagnostics['completed_at_real'] = utc_now()
        diagnostics_path = output_dir / 'discovery_audit.json'
        diagnostics_path.write_text(
            json.dumps(diagnostics, ensure_ascii=False, indent=2,
                       sort_keys=True, default=str) + '\n',
            encoding='utf-8')
        artifact_paths = [
            discovered_path, archive_path, log_path, diagnostics_path]
        manifest = {
            'stage': '4.3', 'run_id': args.run_id,
            'run_kind': 'pilot' if args.pilot_date else 'production_component',
            'source_id': source_id,
            'collector': 'src/stage_4_3_discover_vnexpress.py',
            'collector_version': config['stage_4_3_contract_version'],
            'cdx_used': False,
            'config_sha256': sha256_bytes(CONFIG_PATH.read_bytes()),
            'sources_sha256': sha256_bytes(SOURCES_PATH.read_bytes()),
            'scope_sha256': sha256_bytes(SCOPE_PATH.read_bytes()),
            'artifacts': [
                {
                    'path': str(path.relative_to(ROOT)).replace('\\', '/'),
                    'bytes': path.stat().st_size,
                    'sha256': sha256_bytes(path.read_bytes()),
                }
                for path in artifact_paths
            ],
        }
        (output_dir / 'run_manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2,
                       sort_keys=True) + '\n',
            encoding='utf-8')
    except Exception as exc:
        log({
            'event_type': 'collection_failed',
            'error': f'{type(exc).__name__}: {exc}',
            'discovered_at_real': utc_now(),
        })
        raise
    finally:
        fetcher.close()
    return output_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Stage 4.3 VnExpress no-API discovery collector')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument(
        '--pilot-date', action='append',
        help='ISO date to probe; repeat for a bounded pilot run')
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run(args)
    print(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
