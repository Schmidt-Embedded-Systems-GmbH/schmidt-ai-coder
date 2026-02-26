"""
Markdown formatters for CMSIS-SVD resources.

These formatters generate human-readable markdown for MCP resources,
optimized for "Add Context" in VS Code.
"""

from typing import Any

from mcp_cmsis_svd.model import (
    DeviceSummary,
    PeripheralDetail,
    PeripheralListItem,
    RegisterDetail,
    RegisterListItem,
    FieldDetail,
    FieldInfo,
    DecodedRegister,
    EncodedRegister,
    SearchResult,
)


# Maximum size for resource output (to avoid overwhelming context)
MAX_RESOURCE_SIZE = 10000  # characters


def _truncate(text: str, max_len: int = MAX_RESOURCE_SIZE) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 100] + "\n\n... (output truncated)"


def _escape_markdown(text: str | None) -> str:
    """Escape special markdown characters."""
    if not text:
        return ""
    # Escape backticks and brackets that might interfere with markdown
    return text.replace("`", "\\`").replace("[", "\\[").replace("]", "\\]")


# ============================================================================
# Device Formatters
# ============================================================================

def format_device_summary(device: DeviceSummary) -> str:
    """Format device summary as markdown."""
    lines = [
        f"# {device.name}",
        "",
    ]
    
    if device.vendor:
        lines.append(f"**Vendor:** {device.vendor}")
    
    if device.description:
        lines.append(f"\n{device.description}")
    
    lines.append("")
    lines.append("## Device Information")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Device ID | `{device.device_id}` |")
    
    if device.cpu_name:
        lines.append(f"| CPU | {device.cpu_name} |")
    if device.cpu_revision:
        lines.append(f"| CPU Revision | {device.cpu_revision} |")
    if device.endian:
        lines.append(f"| Endianness | {device.endian} |")
    if device.mpu_present is not None:
        lines.append(f"| MPU | {'Yes' if device.mpu_present else 'No'} |")
    if device.fpu_present is not None:
        lines.append(f"| FPU | {'Yes' if device.fpu_present else 'No'} |")
    if device.nvic_priority_bits is not None:
        lines.append(f"| NVIC Priority Bits | {device.nvic_priority_bits} |")
    
    lines.append("")
    lines.append("## Statistics")
    lines.append("")
    lines.append(f"- **Peripherals:** {device.peripheral_count}")
    lines.append(f"- **Registers:** {device.register_count}")
    lines.append(f"- **Fields:** {device.field_count}")
    
    return _truncate("\n".join(lines))


# ============================================================================
# Peripheral Formatters
# ============================================================================

def format_peripheral_list(peripherals: list[PeripheralListItem]) -> str:
    """Format peripheral list as markdown."""
    if not peripherals:
        return "No peripherals found."
    
    lines = [
        "# Peripherals",
        "",
        "| Name | Base Address | Description |",
        "|------|--------------|-------------|",
    ]
    
    for p in peripherals:
        desc = (p.description[:40] + "...") if p.description and len(p.description) > 40 else (p.description or "")
        lines.append(f"| `{p.name}` | `{p.base_address_hex}` | {_escape_markdown(desc)} |")
    
    return _truncate("\n".join(lines))


def format_peripheral_detail(periph: PeripheralDetail) -> str:
    """Format peripheral detail as markdown."""
    lines = [
        f"# {periph.name}",
        "",
    ]
    
    if periph.description:
        lines.append(f"*{periph.description}*")
        lines.append("")
    
    lines.append("## Properties")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Base Address | `{periph.base_address_hex}` |")
    
    if periph.group_name:
        lines.append(f"| Group | {periph.group_name} |")
    if periph.version:
        lines.append(f"| Version | {periph.version} |")
    if periph.derived_from:
        lines.append(f"| Derived From | `{periph.derived_from}` |")
    
    lines.append(f"| Registers | {periph.register_count} |")
    
    if periph.interrupts:
        lines.append("")
        lines.append("## Interrupts")
        lines.append("")
        lines.append("| Name | IRQ | Description |")
        lines.append("|------|-----|-------------|")
        for intr in periph.interrupts:
            desc = (intr.description[:30] + "...") if intr.description and len(intr.description) > 30 else (intr.description or "")
            lines.append(f"| `{intr.name}` | {intr.value} | {_escape_markdown(desc)} |")
    
    if periph.key_registers:
        lines.append("")
        lines.append("## Key Registers")
        lines.append("")
        for reg in periph.key_registers:
            lines.append(f"- `{reg}`")
    
    lines.append("")
    lines.append(f"*Canonical path: `{periph.canonical_path}`*")
    
    return _truncate("\n".join(lines))


# ============================================================================
# Register Formatters
# ============================================================================

def format_register_list(registers: list[RegisterListItem], peripheral: str) -> str:
    """Format register list as markdown."""
    if not registers:
        return f"No registers found for peripheral '{peripheral}'."
    
    lines = [
        f"# Registers: {peripheral}",
        "",
        "| Register | Offset | Address | Access | Reset | Description |",
        "|----------|--------|---------|--------|-------|-------------|",
    ]
    
    for r in registers:
        desc = (r.description[:25] + "...") if r.description and len(r.description) > 25 else (r.description or "")
        reset = r.reset_value_hex or "-"
        lines.append(
            f"| `{r.display_name}` | `{r.address_offset_hex}` | `{r.absolute_address_hex}` | "
            f"{r.access.value} | `{reset}` | {_escape_markdown(desc)} |"
        )
    
    return _truncate("\n".join(lines))


def format_register_detail(reg: RegisterDetail) -> str:
    """Format register detail as markdown."""
    lines = [
        f"# {reg.peripheral}.{reg.display_name}",
        "",
    ]
    
    if reg.description:
        lines.append(f"*{reg.description}*")
        lines.append("")
    
    lines.append("## Properties")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Offset | `{reg.address_offset_hex}` |")
    lines.append(f"| Absolute Address | `{reg.absolute_address_hex}` |")
    lines.append(f"| Size | {reg.size_bits} bits |")
    lines.append(f"| Access | {reg.access.value} |")
    
    if reg.reset_value_hex:
        lines.append(f"| Reset Value | `{reg.reset_value_hex}` |")
    if reg.reset_mask_hex:
        lines.append(f"| Reset Mask | `{reg.reset_mask_hex}` |")
    
    if reg.fields:
        lines.append("")
        lines.append("## Fields")
        lines.append("")
        lines.append("| Bit(s) | Name | Access | Description |")
        lines.append("|--------|------|--------|-------------|")
        
        for f in reg.fields:
            desc = (f.description[:30] + "...") if f.description and len(f.description) > 30 else (f.description or "")
            lines.append(f"| `{f.bit_range}` | `{f.name}` | {f.access.value} | {_escape_markdown(desc)} |")
        
        # Add field details for fields with enumerated values
        enum_fields = [f for f in reg.fields if f.enumerated_values]
        if enum_fields:
            lines.append("")
            lines.append("## Enumerated Values")
            lines.append("")
            
            for f in enum_fields:
                lines.append(f"### `{f.name}` ({f.bit_range})")
                lines.append("")
                lines.append("| Value | Name | Description |")
                lines.append("|-------|------|-------------|")
                
                for ev in f.enumerated_values:
                    ev_desc = (ev.description[:30] + "...") if ev.description and len(ev.description) > 30 else (ev.description or "")
                    lines.append(f"| `{ev.value_hex}` | `{ev.name}` | {_escape_markdown(ev_desc)} |")
                
                lines.append("")
    
    lines.append(f"*Canonical path: `{reg.canonical_path}`*")
    
    return _truncate("\n".join(lines))


# ============================================================================
# Field Formatters
# ============================================================================

def format_field_detail(field: FieldDetail) -> str:
    """Format field detail as markdown."""
    lines = [
        f"# {field.peripheral}.{field.register}.{field.name}",
        "",
    ]
    
    if field.description:
        lines.append(f"*{field.description}*")
        lines.append("")
    
    lines.append("## Properties")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Bit Range | `{field.bit_range}` |")
    lines.append(f"| Bit Offset | {field.bit_offset} |")
    lines.append(f"| Bit Width | {field.bit_width} |")
    lines.append(f"| Mask | `{field.mask_hex}` |")
    lines.append(f"| Access | {field.access.value} |")
    
    if field.modified_write_values:
        lines.append(f"| Modified Write | {field.modified_write_values} |")
    if field.read_action:
        lines.append(f"| Read Action | {field.read_action} |")
    
    if field.enumerated_values:
        lines.append("")
        lines.append("## Enumerated Values")
        lines.append("")
        lines.append("| Value | Name | Description |")
        lines.append("|-------|------|-------------|")
        
        for ev in field.enumerated_values:
            ev_desc = (ev.description[:40] + "...") if ev.description and len(ev.description) > 40 else (ev.description or "")
            lines.append(f"| `{ev.value_hex}` | `{ev.name}` | {_escape_markdown(ev_desc)} |")
    
    lines.append("")
    lines.append(f"*Canonical path: `{field.canonical_path}`*")
    
    return _truncate("\n".join(lines))


# ============================================================================
# Search Results Formatter
# ============================================================================

def format_search_results(results: list[SearchResult], query: str) -> str:
    """Format search results as markdown."""
    if not results:
        return f"No results found for '{query}'."
    
    lines = [
        f"# Search Results: '{query}'",
        "",
        f"Found {len(results)} matches:",
        "",
    ]
    
    for r in results:
        type_icon = {
            "peripheral": "📦",
            "register": "📋",
            "field": "🔧",
        }.get(r.component_type.value, "📄")
        
        lines.append(f"{type_icon} **`{r.name}`** ({r.component_type.value})")
        lines.append(f"  - Path: `{r.canonical_path}`")
        if r.snippet:
            lines.append(f"  - {r.snippet[:80]}")
        lines.append("")
    
    return _truncate("\n".join(lines))


# ============================================================================
# Decode/Encode Formatters
# ============================================================================

def format_decoded_register(decoded: DecodedRegister) -> str:
    """Format decoded register as markdown."""
    lines = [
        f"# Register Decode: {decoded.peripheral}.{decoded.register}",
        "",
        f"**Input Value:** `{decoded.input_value_hex}` ({decoded.input_value})",
        "",
        "## Field Values",
        "",
        "| Field | Bits | Value | Enum | Description |",
        "|-------|------|-------|------|-------------|",
    ]
    
    for f in decoded.fields:
        enum = f.enumerated_name or "-"
        desc = (f.description[:25] + "...") if f.description and len(f.description) > 25 else (f.description or "")
        lines.append(
            f"| `{f.name}` | `{f.bit_range}` | `{f.raw_value_hex}` | {enum} | {_escape_markdown(desc)} |"
        )
    
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(decoded.markdown_summary)
    
    return _truncate("\n".join(lines))


def format_encoded_register(encoded: EncodedRegister) -> str:
    """Format encoded register as markdown."""
    lines = [
        f"# Register Encode: {encoded.peripheral}.{encoded.register}",
        "",
        f"**Final Value:** `{encoded.final_value_hex}` ({encoded.final_value})",
        "",
        "## Field Contributions",
        "",
        "| Field | Input | Resolved | Mask |",
        "|-------|-------|----------|------|",
    ]
    
    for f in encoded.fields:
        input_val = f"`{f.input_value}`" if isinstance(f.input_value, int) else f"`{f.input_value}`"
        lines.append(
            f"| `{f.name}` | {input_val} | `{f.resolved_value}` | `{hex(f.mask)}` |"
        )
    
    if encoded.warnings:
        lines.append("")
        lines.append("## Warnings")
        lines.append("")
        for w in encoded.warnings:
            lines.append(f"⚠️ {w}")
    
    if encoded.changed_bits:
        lines.append("")
        lines.append("## Changes")
        lines.append("")
        for c in encoded.changed_bits:
            lines.append(f"- {c}")
    
    return _truncate("\n".join(lines))


# ============================================================================
# Bit Field Visualization
# ============================================================================

def format_register_bitmap(reg: RegisterDetail) -> str:
    """Format register as ASCII bit map."""
    if not reg.fields:
        return f"No fields defined for {reg.name}"
    
    lines = [
        f"# {reg.peripheral}.{reg.display_name} - Bit Map",
        "",
        f"Size: {reg.size_bits} bits",
        "",
    ]
    
    # Create a simple bit map
    # Group bits into chunks of 4 for readability
    bit_labels = ["?"] * reg.size_bits
    
    for f in reg.fields:
        for i in range(f.bit_offset, f.bit_offset + f.bit_width):
            if i < reg.size_bits:
                if f.bit_width == 1:
                    bit_labels[i] = f.name[0].upper() if f.name else "?"
                else:
                    bit_labels[i] = f.name[:3] if len(f.name) >= 3 else f.name
    
    # Draw the bit map
    lines.append("```")
    for i in range(reg.size_bits - 1, -1, -1):
        bit_num = i
        label = bit_labels[i] if i < len(bit_labels) else "?"
        lines.append(f"  [{bit_num:2d}] : {label}")
    lines.append("```")
    
    return _truncate("\n".join(lines))
