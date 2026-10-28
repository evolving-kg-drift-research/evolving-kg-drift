"""Vietnamese Natural Language Question Generation for Knowledge Graph QA Panel.

Formulates precise, grammatically correct, formal Vietnamese questions for:
1. 1-hop queries across 10 relation predicates tailored to entity types.
2. 2-hop compositional queries adhering to 'chuẩn ẩn mắt xích' (latent intermediate hop).
"""
from __future__ import annotations

from typing import Sequence

# Canonical predicates defined in protocol and ontology
RELATION_TEMPLATES_1HOP = {
    "works_at": 'Nhân sự/chuyên gia "{h}" đang làm việc hoặc công tác tại cơ quan/tổ chức nào?',
    "is_CEO_of": 'Nhân vật "{h}" đang giữ cương vị Giám đốc điều hành (CEO) của tổ chức/doanh nghiệp nào?',
    "released_by": 'Sản phẩm/công nghệ/mô hình "{h}" do đơn vị hoặc tổ chức nào nghiên cứu và phát hành?',
    "partners_with": 'Tổ chức/doanh nghiệp "{h}" thiết lập quan hệ hợp tác chiến lược với đơn vị nào?',
    "invested_in": 'Tổ chức "{h}" đã thực hiện khoản rót vốn đầu tư chiến lược vào đơn vị nào?',
    "version_of": 'Thiết bị/phiên bản "{h}" là một biến thể cấu hình trực thuộc dòng sản phẩm/hệ điều hành nào?',
    "integrated_into": 'Tính năng/thành phần công nghệ "{h}" được tích hợp trực tiếp vào sản phẩm/hệ thống nào?',
    "based_on": 'Sản phẩm/công nghệ "{h}" được phát triển dựa trên nền tảng kỹ thuật nào?',
    "succeeded_by": 'Thiết bị/sản phẩm "{h}" được kế nhiệm hoặc thay thế bởi dòng thiết bị nào?',
    "acquired_by": 'Doanh nghiệp/thực thể "{h}" đã được sáp nhập hoặc mua lại bởi nhân vật/tổ chức nào?',
}

# 2-hop latent bridge templates (chuẩn ẩn mắt xích: không để lộ danh tính thực thể trung gian)
RELATION_TEMPLATES_2HOP = {
    ("works_at", "partners_with"): (
        'Cơ quan/tổ chức nơi nhân sự/chuyên gia "{h}" đang công tác đã thiết lập quan hệ hợp tác chiến lược với đơn vị nào?'
    ),
    ("released_by", "partners_with"): (
        'Đơn vị nghiên cứu và phát hành sản phẩm/công nghệ "{h}" đã thiết lập quan hệ hợp tác chiến lược với tổ chức nào?'
    ),
    ("works_at", "invested_in"): (
        'Cơ quan/tổ chức nơi chuyên gia/nhân sự "{h}" đang công tác đã thực hiện khoản rót vốn đầu tư chiến lược vào đơn vị nào?'
    ),
    ("integrated_into", "released_by"): (
        'Sản phẩm/hệ thống tích hợp thành phần công nghệ "{h}" do đơn vị hoặc tổ chức nào nghiên cứu và phát hành?'
    ),
    ("is_CEO_of", "partners_with"): (
        'Tổ chức/doanh nghiệp do nhân vật "{h}" giữ cương vị CEO đã thiết lập quan hệ hợp tác chiến lược với đơn vị nào?'
    ),
    ("version_of", "succeeded_by"): (
        'Dòng sản phẩm mà thiết bị/phiên bản "{h}" trực thuộc được kế nhiệm hoặc thay thế bởi dòng thiết bị nào?'
    ),
    ("partners_with", "partners_with"): (
        'Đối tác chiến lược của đơn vị/tổ chức đang hợp tác cùng "{h}" là tổ chức nào?'
    ),
    ("based_on", "released_by"): (
        'Đơn vị nào nghiên cứu và phát hành nền tảng kỹ thuật làm cơ sở phát triển của sản phẩm/công nghệ "{h}"?'
    ),
    ("acquired_by", "works_at"): (
        'Nhân vật/thực thể đã mua lại doanh nghiệp "{h}" hiện đang làm việc hoặc công tác tại cơ quan/tổ chức nào?'
    ),
    ("invested_in", "partners_with"): (
        'Đơn vị nhận khoản rót vốn đầu tư chiến lược từ tổ chức "{h}" đã thiết lập quan hệ hợp tác chiến lược với tổ chức nào?'
    ),
    ("succeeded_by", "version_of"): (
        'Thiết bị kế nhiệm dòng sản phẩm "{h}" là một biến thể cấu hình trực thuộc dòng sản phẩm nào?'
    ),
}

# Keyword sets for fine-grained entity typing
_AI_MODELS = {
    "deepseek", "gpt", "gemini", "gemma", "o1", "r1", "ai agents",
    "brainmedqwen", "nomi", "nvidia cosmos", "chatgpt"
}
_DEVICES = {
    "iphone", "galaxy", "camera", "iq", "play", "màn hình",
    "newton", "tcl", "tianmushan", "redmi", "s25", "blackwell"
}
_OS_PLATFORMS = {"macos", "ios", "ipados", "android"}
_EVENTS = {"pitchfest"}
_SCIENTISTS = {"ts ", "tiến sĩ", "giáo sư", "dr."}


def infer_entity_kind(name: str) -> str:
    """Infer coarse-grained semantic category for entity name."""
    lower = name.lower()
    if any(lower.startswith(p) for p in _SCIENTISTS):
        return "SCIENTIST"
    if any(keyword in lower for keyword in _EVENTS):
        return "EVENT"
    if any(keyword in lower for keyword in _DEVICES):
        return "DEVICE"
    if any(keyword in lower for keyword in _OS_PLATFORMS):
        return "OS"
    if any(keyword in lower for keyword in _AI_MODELS):
        return "AI_MODEL"
    return "GENERAL"


def format_1hop_question(head_name: str, relation_name: str) -> str:
    """Generate formal Vietnamese question for 1-hop triple tailored to entity type."""
    h = head_name.strip()
    kind = infer_entity_kind(h)

    if relation_name == "works_at":
        if kind == "SCIENTIST" or h in {"Lê Viết Quốc", "Robert Jarolim", "Robert Sternberg", "Stefania Druga"}:
            return f'Chuyên gia/nhà nghiên cứu "{h}" đang làm việc hoặc công tác tại cơ quan/tổ chức nào?'
        return f'Nhân sự/chuyên gia "{h}" đang làm việc hoặc công tác tại cơ quan/tổ chức nào?'

    if relation_name == "is_CEO_of":
        return f'Nhân vật "{h}" đang giữ cương vị Giám đốc điều hành (CEO) của tổ chức/doanh nghiệp nào?'

    if relation_name == "released_by":
        if kind == "AI_MODEL":
            return f'Mô hình/hệ thống AI "{h}" do đơn vị hoặc tổ chức nào nghiên cứu và phát hành?'
        if kind == "DEVICE":
            return f'Sản phẩm/thiết bị "{h}" do đơn vị hoặc tổ chức nào nghiên cứu và phát hành?'
        return f'Sản phẩm/công nghệ/mô hình "{h}" do đơn vị hoặc tổ chức nào nghiên cứu và phát hành?'

    if relation_name == "partners_with":
        return f'Tổ chức/doanh nghiệp "{h}" thiết lập quan hệ hợp tác chiến lược với đơn vị nào?'

    if relation_name == "invested_in":
        return f'Tổ chức "{h}" đã thực hiện khoản rót vốn đầu tư chiến lược vào đơn vị nào?'

    if relation_name == "version_of":
        if kind == "OS":
            return f'Hệ điều hành/phiên bản "{h}" là một biến thể cấu hình trực thuộc dòng sản phẩm/hệ điều hành nào?'
        if kind == "EVENT":
            return f'Sự kiện/chương trình "{h}" là phiên bản kế tiếp trực thuộc chuỗi sự kiện nào?'
        if kind == "AI_MODEL":
            return f'Mô hình/phiên bản "{h}" là một biến thể cấu hình trực thuộc dòng sản phẩm/mô hình nào?'
        if kind == "DEVICE":
            return f'Thiết bị/phiên bản "{h}" là một biến thể cấu hình trực thuộc dòng sản phẩm nào?'
        return f'Thiết bị/phiên bản "{h}" là một biến thể cấu hình trực thuộc dòng sản phẩm/hệ điều hành nào?'

    if relation_name == "integrated_into":
        if "ring" in h.lower():
            return f'Thiết bị/thành phần công nghệ "{h}" được tích hợp trực tiếp vào sản phẩm/hệ thống nào?'
        return f'Tính năng/thành phần công nghệ "{h}" được tích hợp trực tiếp vào sản phẩm/hệ thống nào?'

    if relation_name == "based_on":
        return f'Sản phẩm/công nghệ "{h}" được phát triển dựa trên nền tảng kỹ thuật nào?'

    if relation_name == "succeeded_by":
        if kind == "EVENT":
            return f'Sự kiện/chương trình "{h}" được kế nhiệm hoặc thay thế bởi sự kiện/chương trình nào?'
        return f'Thiết bị/sản phẩm "{h}" được kế nhiệm hoặc thay thế bởi dòng thiết bị nào?'

    if relation_name == "acquired_by":
        return f'Doanh nghiệp/thực thể "{h}" đã được sáp nhập hoặc mua lại bởi nhân vật/tổ chức nào?'

    template = RELATION_TEMPLATES_1HOP.get(relation_name)
    if template:
        return template.format(h=h)
    return f'Thực thể "{h}" có mối quan hệ "{relation_name}" với thực thể nào?'


def format_2hop_question(head_name: str, relation_path: Sequence[str]) -> str:
    """Generate compositional Vietnamese question hiding the intermediate entity (chuẩn ẩn mắt xích)."""
    h = head_name.strip()
    key = (relation_path[0], relation_path[1])
    template = RELATION_TEMPLATES_2HOP.get(key)
    if template:
        return template.format(h=h)

    # General fallback for arbitrary 2-hop compositions:
    r1, r2 = relation_path[0], relation_path[1]
    return f'Thực thể có mối liên kết qua chuỗi quan hệ [{r1} -> {r2}] bắt đầu từ "{h}" là thực thể nào?'


def format_qa_question(head_name: str, relation_path: Sequence[str]) -> str:
    """Unified natural language question formatter for 1-hop and multi-hop queries."""
    if len(relation_path) == 1:
        return format_1hop_question(head_name, relation_path[0])
    if len(relation_path) == 2:
        return format_2hop_question(head_name, relation_path)
    # n-hop fallback
    chain = " -> ".join(relation_path)
    return f'Bắt đầu từ "{head_name}", thực thể đích liên kết qua chuỗi quan hệ [{chain}] là gì?'
