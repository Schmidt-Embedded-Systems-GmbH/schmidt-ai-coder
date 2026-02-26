"""
CMSIS-SVD MCP Server - Main entry point.

This FastMCP 3.x server exposes CMSIS-SVD device metadata to LLM agents
for embedded debugging in VS Code.

Features:
- Load and parse SVD files
- Query peripherals, registers, and fields
- Decode/encode register values
- Search and resolve components
- Markdown resources for context
"""

import json
import sys
from typing import Any

import cmsis_svd  # For validation of derived peripherals
from fastmcp import FastMCP, Context

from mcp_cmsis_svd.svd_store import get_store, SVDStore
from mcp_cmsis_svd.model import (
    DeviceLoadResult,
    DeviceSummary,
    PeripheralListItem,
    PeripheralDetail,
    RegisterListItem,
    RegisterDetail,
    FieldDetail,
    SearchResult,
    SearchResultList,
    ResolvedComponent,
    DecodedRegister,
    DecodedField,
    EncodedRegister,
    EncodedField,
    ValidationResult,
    ValidationIssue,
)
from mcp_cmsis_svd.formatters import (
    format_device_summary,
    format_peripheral_list,
    format_peripheral_detail,
    format_register_list,
    format_register_detail,
    format_field_detail,
    format_search_results,
    format_decoded_register,
    format_encoded_register,
)


# ============================================================================
# FastMCP Server Instance
# ============================================================================

mcp = FastMCP(
    name="CMSIS-SVD Server",
    instructions="""
This server provides access to CMSIS-SVD device metadata for embedded debugging.

Workflow:
1. Load an SVD file using `svd_load` to set the active device
2. Query peripherals, registers, and fields using the various tools
3. Use `svd_decode_register_value` to interpret register values
4. Use `svd_encode_register_value` to compute register values from fields

All tools default to the active device unless a device_id is specified.
Use canonical paths (e.g., "REG:GPIOA.ODR") for precise lookups.
""",
)


# ============================================================================
# Helper Functions
# ============================================================================

def _get_active_device_id(ctx: Context) -> str | None:
    """Get the active device ID from context or store."""
    store = get_store()
    cached = store.get_active_device()
    return cached.device_id if cached else None


def _require_active_device(ctx: Context) -> tuple[SVDStore, str]:
    """Get store and active device ID, raising error if no device loaded."""
    store = get_store()
    cached = store.get_active_device()
    if not cached:
        raise ValueError("No SVD file loaded. Use svd_load first.")
    return store, cached.device_id


# ============================================================================
# Tools - Device Management
# ============================================================================

@mcp.tool()
async def svd_load(
    path: str,
    strict: bool = False,
    ctx: Context = None,
) -> dict:
    """
    Load and parse an SVD file, setting it as the active device.
    
    Args:
        path: Path to the SVD file (.svd or .xml)
        strict: Enable strict parsing mode (default: False)
    
    Returns:
        Device load result with device_id and summary, or error message
    """
    store = get_store()
    result = store.load(path, strict)
    
    if result.success:
        await ctx.info(f"Loaded SVD: {result.device.name}")
    else:
        await ctx.error(f"Failed to load SVD: {result.error}")
    
    return result.model_dump()


@mcp.tool()
async def svd_device_summary(
    device_id: str | None = None,
    ctx: Context = None,
) -> dict:
    """
    Get summary of the active or specified device.
    
    Args:
        device_id: Optional device ID (defaults to active device)
    
    Returns:
        Device summary with metadata and statistics
    """
    store = get_store()
    cached = store.get_device(device_id)
    
    if not cached:
        return {"error": "No device loaded" if not device_id else f"Device not found: {device_id}"}
    
    return cached.summary.model_dump()


# ============================================================================
# Tools - Peripheral Access
# ============================================================================

@mcp.tool()
async def svd_list_peripherals(
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    device_id: str | None = None,
    ctx: Context = None,
) -> dict:
    """
    List peripherals in the device with optional filtering.
    
    Args:
        filter: Optional filter string (case-insensitive substring match)
        limit: Maximum number of results (default: 50)
        offset: Offset for pagination (default: 0)
        device_id: Optional device ID (defaults to active device)
    
    Returns:
        List of peripherals with name, base address, and description
    """
    store = get_store()
    
    if not device_id:
        _, device_id = _require_active_device(ctx)
    
    peripherals = store.list_peripherals(device_id, filter, limit, offset)
    
    return {
        "total_count": len(peripherals),
        "filter": filter,
        "peripherals": [p.model_dump() for p in peripherals],
    }


@mcp.tool()
async def svd_get_peripheral(
    peripheral: str,
    device_id: str | None = None,
    ctx: Context = None,
) -> dict:
    """
    Get detailed information about a peripheral.
    
    Args:
        peripheral: Peripheral name (case-insensitive)
        device_id: Optional device ID (defaults to active device)
    
    Returns:
        Peripheral details including registers, interrupts, and properties
    """
    store = get_store()
    
    if not device_id:
        _, device_id = _require_active_device(ctx)
    
    result = store.get_peripheral(peripheral, device_id)
    
    if not result:
        return {"error": f"Peripheral not found: {peripheral}"}
    
    return result.model_dump()


# ============================================================================
# Tools - Register Access
# ============================================================================

@mcp.tool()
async def svd_list_registers(
    peripheral: str,
    limit: int = 100,
    offset: int = 0,
    device_id: str | None = None,
    ctx: Context = None,
) -> dict:
    """
    List registers for a peripheral.
    
    Args:
        peripheral: Peripheral name (case-insensitive)
        limit: Maximum number of results (default: 100)
        offset: Offset for pagination (default: 0)
        device_id: Optional device ID (defaults to active device)
    
    Returns:
        List of registers with addresses, access, and reset values
    """
    store = get_store()
    
    if not device_id:
        _, device_id = _require_active_device(ctx)
    
    registers = store.list_registers(peripheral, device_id, limit, offset)
    
    if not registers:
        return {"error": f"No registers found for peripheral: {peripheral}", "registers": []}
    
    return {
        "peripheral": peripheral,
        "total_count": len(registers),
        "registers": [r.model_dump() for r in registers],
    }


@mcp.tool()
async def svd_get_register(
    peripheral: str,
    register: str,
    device_id: str | None = None,
    ctx: Context = None,
) -> dict:
    """
    Get detailed information about a register including fields.
    
    Args:
        peripheral: Peripheral name (case-insensitive)
        register: Register name (case-insensitive)
        device_id: Optional device ID (defaults to active device)
    
    Returns:
        Register details including all fields with bit ranges and enumerated values
    """
    store = get_store()
    
    if not device_id:
        _, device_id = _require_active_device(ctx)
    
    result = store.get_register(peripheral, register, device_id)
    
    if not result:
        return {"error": f"Register not found: {peripheral}.{register}"}
    
    return result.model_dump()


# ============================================================================
# Tools - Field Access
# ============================================================================

@mcp.tool()
async def svd_get_field(
    peripheral: str,
    register: str,
    field: str,
    device_id: str | None = None,
    ctx: Context = None,
) -> dict:
    """
    Get detailed information about a field.
    
    Args:
        peripheral: Peripheral name (case-insensitive)
        register: Register name (case-insensitive)
        field: Field name (case-insensitive)
        device_id: Optional device ID (defaults to active device)
    
    Returns:
        Field details including bit range, mask, access, and enumerated values
    """
    store = get_store()
    
    if not device_id:
        _, device_id = _require_active_device(ctx)
    
    result = store.get_field(peripheral, register, field, device_id)
    
    if not result:
        return {"error": f"Field not found: {peripheral}.{register}.{field}"}
    
    return result.model_dump()


# ============================================================================
# Tools - Search and Resolve
# ============================================================================

@mcp.tool()
async def svd_search(
    query: str,
    kind: str = "any",
    limit: int = 20,
    device_id: str | None = None,
    ctx: Context = None,
) -> dict:
    """
    Search for peripherals, registers, or fields by name.
    
    Args:
        query: Search query (case-insensitive substring match)
        kind: Type filter - "peripheral", "register", "field", or "any" (default)
        limit: Maximum number of results (default: 20)
        device_id: Optional device ID (defaults to active device)
    
    Returns:
        Search results with canonical paths and snippets
    """
    store = get_store()
    
    if not device_id:
        _, device_id = _require_active_device(ctx)
    
    if kind not in ("any", "peripheral", "register", "field"):
        return {"error": f"Invalid kind: {kind}. Must be 'any', 'peripheral', 'register', or 'field'"}
    
    results = store.search(query, kind, limit, device_id)
    
    return SearchResultList(
        query=query,
        kind=kind,
        total_results=len(results),
        returned_count=len(results),
        results=results,
    ).model_dump()


@mcp.tool()
async def svd_resolve(
    path: str,
    device_id: str | None = None,
    ctx: Context = None,
) -> dict:
    """
    Resolve a canonical path or dotted path to a component.
    
    Args:
        path: Canonical path (e.g., "REG:GPIOA.ODR") or dotted path (e.g., "GPIOA.ODR")
        device_id: Optional device ID (defaults to active device)
    
    Returns:
        Resolved component with type, address, and properties
    """
    store = get_store()
    
    if not device_id:
        _, device_id = _require_active_device(ctx)
    
    result = store.resolve(path, device_id)
    
    if not result:
        return {"error": f"Component not found: {path}"}
    
    return result.model_dump()


# ============================================================================
# Tools - Decode/Encode
# ============================================================================

@mcp.tool()
async def svd_decode_register_value(
    peripheral: str,
    register: str,
    value: int,
    device_id: str | None = None,
    ctx: Context = None,
) -> dict:
    """
    Decode a register value into field values.
    
    Args:
        peripheral: Peripheral name
        register: Register name
        value: Register value to decode (integer)
        device_id: Optional device ID (defaults to active device)
    
    Returns:
        Decoded register with field values and enumerated names
    """
    store = get_store()
    
    if not device_id:
        _, device_id = _require_active_device(ctx)
    
    # Get register details
    reg = store.get_register(peripheral, register, device_id)
    if not reg:
        return {"error": f"Register not found: {peripheral}.{register}"}
    
    # Decode each field
    decoded_fields = []
    markdown_lines = []
    
    for f in reg.fields:
        # Extract field value
        field_value = (value & f.mask) >> f.bit_offset
        
        # Look up enumerated value
        enum_name = None
        enum_desc = None
        for ev in f.enumerated_values:
            if ev.value == field_value:
                enum_name = ev.name
                enum_desc = ev.description
                break
        
        decoded_fields.append(DecodedField(
            name=f.name,
            bit_range=f.bit_range,
            raw_value=field_value,
            raw_value_hex=f"0x{field_value:X}",
            enumerated_name=enum_name,
            enumerated_description=enum_desc,
            description=f.description,
        ))
        
        # Build markdown line
        if enum_name:
            markdown_lines.append(f"- **{f.name}** [{f.bit_range}]: `{field_value}` = `{enum_name}`")
        else:
            markdown_lines.append(f"- **{f.name}** [{f.bit_range}]: `{field_value}`")
    
    result = DecodedRegister(
        peripheral=peripheral,
        register=register,
        input_value=value,
        input_value_hex=f"0x{value:X}",
        fields=decoded_fields,
        markdown_summary="\n".join(markdown_lines),
    )
    
    return result.model_dump()


@mcp.tool()
async def svd_encode_register_value(
    peripheral: str,
    register: str,
    field_values: dict[str, int | str],
    base_value: int = 0,
    device_id: str | None = None,
    ctx: Context = None,
) -> dict:
    """
    Encode field values into a register value.
    
    Args:
        peripheral: Peripheral name
        register: Register name
        field_values: Dict mapping field names to values (int or enum name)
        base_value: Starting value to build upon (default: 0)
        device_id: Optional device ID (defaults to active device)
    
    Returns:
        Encoded register with final value and field contributions
    """
    store = get_store()
    
    if not device_id:
        _, device_id = _require_active_device(ctx)
    
    # Get register details
    reg = store.get_register(peripheral, register, device_id)
    if not reg:
        return {"error": f"Register not found: {peripheral}.{register}"}
    
    # Build field lookup
    field_lookup = {f.name.lower(): f for f in reg.fields}
    
    final_value = base_value
    encoded_fields = []
    warnings = []
    changed_bits = []
    
    for field_name, input_val in field_values.items():
        # Find field (case-insensitive)
        f = field_lookup.get(field_name.lower())
        if not f:
            warnings.append(f"Field not found: {field_name}")
            continue
        
        # Resolve value
        resolved_value = None
        
        if isinstance(input_val, str):
            # Try to match enumerated value
            for ev in f.enumerated_values:
                if ev.name.lower() == input_val.lower():
                    resolved_value = ev.value
                    break
            
            if resolved_value is None:
                # Try parsing as integer string
                try:
                    resolved_value = int(input_val, 0)
                except ValueError:
                    warnings.append(f"Invalid value for {field_name}: {input_val}")
                    continue
        else:
            resolved_value = input_val
        
        # Validate range
        max_val = (1 << f.bit_width) - 1
        if resolved_value < 0 or resolved_value > max_val:
            warnings.append(f"Value {resolved_value} out of range for {field_name} (0-{max_val})")
            resolved_value = resolved_value & max_val  # Truncate
        
        # Compute shifted value
        shifted_value = resolved_value << f.bit_offset
        
        # Clear field bits in final value, then set
        final_value = (final_value & ~f.mask) | shifted_value
        
        encoded_fields.append(EncodedField(
            name=f.name,
            input_value=input_val,
            resolved_value=resolved_value,
            mask=f.mask,
            shifted_value=shifted_value,
        ))
        
        changed_bits.append(f"{f.name}: bits {f.bit_range} = {resolved_value}")
    
    result = EncodedRegister(
        peripheral=peripheral,
        register=register,
        base_value=base_value,
        final_value=final_value,
        final_value_hex=f"0x{final_value:X}",
        fields=encoded_fields,
        warnings=warnings,
        changed_bits=changed_bits,
    )
    
    return result.model_dump()


# ============================================================================
# Tools - Validation (Optional)
# ============================================================================

@mcp.tool()
async def svd_validate(
    path: str | None = None,
    device_id: str | None = None,
    ctx: Context = None,
) -> dict:
    """
    Validate an SVD file (schema validation only, svdconv not integrated).
    
    Args:
        path: Path to SVD file (defaults to active device's file)
        device_id: Optional device ID (defaults to active device)
    
    Returns:
        Validation result with any issues found
    """
    store = get_store()
    
    # If path provided, try to load it first
    if path:
        result = store.load(path)
        if not result.success:
            return ValidationResult(
                valid=False,
                issues=[ValidationIssue(
                    severity="error",
                    message=result.error,
                )],
                tool_used="parser",
            ).model_dump()
    
    # Get device
    cached = store.get_device(device_id)
    if not cached:
        return {"error": "No device loaded"}
    
    # Basic validation - check for common issues
    issues = []
    
    # Check for peripherals without registers
    for name, periph in cached.peripheral_index.items():
        regs = cached.register_index.keys()
        has_regs = any(p == name for p, _ in regs)
        if not has_regs:
            # Check if derived
            if hasattr(periph, 'derived_from') and periph.derived_from:
                continue  # Derived peripherals inherit registers
            issues.append(ValidationIssue(
                severity="warning",
                component=f"PERIPHERAL:{name}",
                message=f"Peripheral '{name}' has no registers defined",
            ))
    
    return ValidationResult(
        valid=len([i for i in issues if i.severity == "error"]) == 0,
        issues=issues,
        tool_used="parser",
    ).model_dump()


# ============================================================================
# Resources - Device
# ============================================================================

@mcp.resource("svd://device")
async def resource_device() -> str:
    """Get device summary as markdown."""
    store = get_store()
    cached = store.get_active_device()
    
    if not cached:
        return "# No Device Loaded\n\nUse `svd_load` to load an SVD file first."
    
    return format_device_summary(cached.summary)


# ============================================================================
# Resources - Peripherals
# ============================================================================

@mcp.resource("svd://peripheral/{name}")
async def resource_peripheral(name: str) -> str:
    """Get peripheral details as markdown."""
    store = get_store()
    cached = store.get_active_device()
    
    if not cached:
        return "# No Device Loaded\n\nUse `svd_load` to load an SVD file first."
    
    periph = store.get_peripheral(name)
    
    if not periph:
        return f"# Peripheral Not Found\n\nPeripheral '{name}' not found in device."
    
    return format_peripheral_detail(periph)


# ============================================================================
# Resources - Registers
# ============================================================================

@mcp.resource("svd://peripheral/{p}/register/{r}")
async def resource_register(p: str, r: str) -> str:
    """Get register details as markdown."""
    store = get_store()
    cached = store.get_active_device()
    
    if not cached:
        return "# No Device Loaded\n\nUse `svd_load` to load an SVD file first."
    
    reg = store.get_register(p, r)
    
    if not reg:
        return f"# Register Not Found\n\nRegister '{p}.{r}' not found."
    
    return format_register_detail(reg)


# ============================================================================
# Resources - Fields
# ============================================================================

@mcp.resource("svd://peripheral/{p}/register/{r}/field/{f}")
async def resource_field(p: str, r: str, f: str) -> str:
    """Get field details as markdown."""
    store = get_store()
    cached = store.get_active_device()
    
    if not cached:
        return "# No Device Loaded\n\nUse `svd_load` to load an SVD file first."
    
    field = store.get_field(p, r, f)
    
    if not field:
        return f"# Field Not Found\n\nField '{p}.{r}.{f}' not found."
    
    return format_field_detail(field)


# ============================================================================
# Resources - Search
# ============================================================================

@mcp.resource("svd://search?q={query}")
async def resource_search(query: str) -> str:
    """Search SVD components as markdown."""
    store = get_store()
    cached = store.get_active_device()
    
    if not cached:
        return "# No Device Loaded\n\nUse `svd_load` to load an SVD file first."
    
    results = store.search(query, "any", 30)
    
    return format_search_results(results, query)


# ============================================================================
# Prompts
# ============================================================================

@mcp.prompt()
async def svd_explain_register(peripheral: str, register: str) -> str:
    """
    Explain a register's purpose and fields.
    
    Use this prompt to get a detailed explanation of a register.
    
    Args:
        peripheral: Peripheral name
        register: Register name
    """
    return f"""Please explain the {peripheral}.{register} register:

1. First, call svd_get_register(peripheral="{peripheral}", register="{register}") to get the register details
2. Summarize the register's purpose based on its description
3. List all fields with their bit ranges and purposes
4. Highlight any fields with enumerated values and explain what each value means
5. Note the reset value and what it implies about the initial state
6. Mention any important access restrictions (read-only, write-only, etc.)

Format the explanation in a clear, educational style suitable for an embedded developer."""


@mcp.prompt()
async def svd_decode_value(peripheral: str, register: str, value_hex: str) -> str:
    """
    Decode a register value and explain what it represents.
    
    Use this prompt to understand what a register value means.
    
    Args:
        peripheral: Peripheral name
        register: Register name
        value_hex: Register value in hex (e.g., "0x12345678")
    """
    return f"""Please decode and explain the value {value_hex} for {peripheral}.{register}:

1. First, convert the hex value to an integer: int("{value_hex}", 16)
2. Call svd_decode_register_value(peripheral="{peripheral}", register="{register}", value=<integer>)
3. For each field, explain what the value means:
   - If the field has enumerated values, show the enum name
   - Explain the practical meaning of each field value
4. Summarize the overall configuration represented by this register value

Format as a clear explanation suitable for debugging."""


@mcp.prompt()
async def svd_find_related(keyword: str) -> str:
    """
    Find peripherals, registers, and fields related to a keyword.
    
    Use this prompt to discover components related to a feature or function.
    
    Args:
        keyword: Search keyword (e.g., "timer", "interrupt", "gpio")
    """
    return f"""Please find all components related to "{keyword}":

1. Call svd_search(query="{keyword}", kind="any", limit=30)
2. Group the results by type (peripherals, registers, fields)
3. For the most relevant results, fetch additional details:
   - For peripherals: svd_get_peripheral
   - For registers: svd_get_register
4. Summarize how these components relate to "{keyword}"
5. Suggest which components are most important for understanding this feature

Format as a structured overview with canonical paths for easy reference."""


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the MCP server."""
    # Run the FastMCP server
    mcp.run()


if __name__ == "__main__":
    main()
