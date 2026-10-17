# Data distribution

## Repository scope

This repository versions only the materials needed to review and reproduce the implementation:

- source code, tests, and development tooling;
- configuration and small, deliberately selected metadata/manifests;
- documentation and source-reference materials.

Raw corpus files, discovery output, pipeline run artifacts, logs, reports, caches, and generated data products are local or externally distributed artifacts. They are not part of Git history and must not be added by bulk staging.

In particular, the following local paths are excluded from normal Git commits:

- `data/raw/`
- `data/discovery/`
- `data/stage_4_3_runs/`
- `data/stage_4_4_runs/`
- `data/stage_4_4/`
- `runs/`, `logs/`, `reports/`, and `outputs/`

Small files under `data/manifests/` are not automatically approved for versioning. Add one only when its purpose, provenance, and review scope have been validated separately.

## Current readiness

There is **no production data release** in this version of the repository. Ticket A / Gate A is currently **BLOCKED**. The retained Ticket A implementation inventories inputs and produces readiness evidence; it does not establish that the local corpus is production-ready.

This repository also contains no Ticket B or local-LLM implementation. Any future Hosted LLM work requires explicit approval and must be introduced as new, versioned work after Gate A requirements are satisfied.

## Collaborator workflow

1. Clone the repository.
2. Create a Python environment and install the locked dependencies from `requirements.lock.txt`.
3. Run the test suite before using pipeline code:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   ```

4. For full inventory execution, obtain an approved external dataset package. Do not expect raw data or historical run outputs to be present after cloning.
5. Verify the supplied package before use, then follow its unpack instructions without changing the package's declared provenance or hashes.

Code-only checks and tests can run without a production dataset release where the test fixture scope permits it. Full inventory requires an externally supplied package compatible with the run configuration.

## Future external dataset package contract

A future distribution package must be versioned independently from this Git repository and include, at minimum:

- `dataset_id` and dataset version;
- gate status and the evidence/run identifier supporting that status;
- declared scope, including source/time/coverage boundaries;
- a manifest enumerating distributed files;
- SHA-256 checksums for the package and relevant contents;
- unpack and expected-path instructions;
- source licensing, permissions, and any redistribution restrictions;
- verification instructions that reproduce checksum and manifest validation.

Consumers must verify SHA-256 values and manifest contents before unpacking or running inventory. A package may not be presented as production-ready unless its documented gate status and evidence support that claim.
