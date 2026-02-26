"""
Pydantic models for CMSIS-SVD MCP tool outputs.

These models provide structured, typed outputs for all SVD tools,
optimized for LLM consumption with clear field names and documentation.
"""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class AccessType(str, Enum):
    """Register/field access type."""
    READ_ONLY = "read-only"
    WRITE_ONLY = "write-only"
    READ_WRITE = "read-write"
    READ_WRITE_ONCE = "read-write-once"
    WRITE_ONCE = "write-once"
    UNKNOWN = "unknown"


class ComponentType(str, Enum):
    """Type of SVD component."""
    PERIPHERAL = "peripheral"
    REGISTER = "register"
    FIELD = "field"
    CLUSTER = "cluster"


# ============================================================================
# Device Models
# ============================================================================

class DeviceSummary(BaseModel):
    """Summary of a loaded SVD device."""
    model_config = ConfigDict(populate_by_name=True)
    
    device_id: str = Field(..., description="Unique identifier for the loaded device")
    name: str = Field(..., description="Device name from SVD")
    vendor: str | None = Field(None, description="Vendor name")
    description: str | None = Field(None, description="Device description")
    cpu_name: str | None = Field(None, description="CPU name (e.g., CM4)")
    cpu_revision: str | None = Field(None, description="CPU revision")
    endian: str | None = Field(None, description="Endianness (little/big)")
    mpu_present: bool | None = Field(None, description="Whether MPU is present")
    fpu_present: bool | None = Field(None, description="Whether FPU is present")
    nvic_priority_bits: int | None = Field(None, description="Number of NVIC priority bits")
    vendor_systick_config: bool | None = Field(None, description="Vendor SysTick configuration")
    peripheral_count: int = Field(..., description="Total number of peripherals")
    register_count: int = Field(..., description="Total number of registers")
    field_count: int = Field(..., description="Total number of fields")
    address_unit_bits: int | None = Field(None, description="Address unit bits (usually 8)")


class DeviceLoadResult(BaseModel):
    """Result of loading an SVD file."""
    model_config = ConfigDict(populate_by_name=True)
    
    success: bool = Field(..., description="Whether loading succeeded")
    device_id: str | None = Field(None, description="Unique device identifier if successful")
    device: DeviceSummary | None = Field(None, description="Device summary if successful")
    error: str | None = Field(None, description="Error message if failed")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings during parsing")


# ============================================================================
# Peripheral Models
# ============================================================================

class PeripheralListItem(BaseModel):
    """Brief peripheral info for list views."""
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., description="Peripheral name")
    base_address_hex: str = Field(..., description="Base address in hex (0x...)")
    base_address: int = Field(..., description="Base address as integer")
    description: str | None = Field(None, description="Short description")
    group_name: str | None = Field(None, description="Group name for categorization")
    derived_from: str | None = Field(None, description="Name of peripheral this derives from")
    canonical_path: str = Field(..., description="Canonical path: PERIPHERAL:<name>")


class InterruptInfo(BaseModel):
    """Interrupt information for a peripheral."""
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., description="Interrupt name")
    value: int = Field(..., description="Interrupt number/IRQ")
    description: str | None = Field(None, description="Interrupt description")


class PeripheralDetail(BaseModel):
    """Detailed peripheral information."""
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., description="Peripheral name")
    base_address_hex: str = Field(..., description="Base address in hex")
    base_address: int = Field(..., description="Base address as integer")
    description: str | None = Field(None, description="Full description")
    group_name: str | None = Field(None, description="Group name")
    version: str | None = Field(None, description="Peripheral version")
    derived_from: str | None = Field(None, description="Derived from peripheral name")
    register_count: int = Field(..., description="Number of registers")
    cluster_count: int = Field(0, description="Number of clusters")
    interrupts: list[InterruptInfo] = Field(default_factory=list, description="Associated interrupts")
    key_registers: list[str] = Field(default_factory=list, description="Names of important registers")
    canonical_path: str = Field(..., description="Canonical path")


# ============================================================================
# Register Models
# ============================================================================

class RegisterListItem(BaseModel):
    """Brief register info for list views."""
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., description="Register name")
    display_name: str = Field(..., description="Name with array index if applicable")
    address_offset_hex: str = Field(..., description="Offset from peripheral base in hex")
    address_offset: int = Field(..., description="Offset as integer")
    absolute_address_hex: str = Field(..., description="Absolute address in hex")
    absolute_address: int = Field(..., description="Absolute address as integer")
    size_bits: int = Field(32, description="Register size in bits")
    access: AccessType = Field(AccessType.UNKNOWN, description="Access type")
    reset_value_hex: str | None = Field(None, description="Reset value in hex")
    description: str | None = Field(None, description="Short description")
    canonical_path: str = Field(..., description="Canonical path: REG:<peripheral>.<register>")


class EnumeratedValueInfo(BaseModel):
    """Enumerated value for a field."""
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., description="Enumeration name")
    value: int = Field(..., description="Enumeration value")
    value_hex: str = Field(..., description="Value in hex")
    description: str | None = Field(None, description="Value description")


class FieldInfo(BaseModel):
    """Detailed field information."""
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., description="Field name")
    bit_offset: int = Field(..., description="Bit offset within register")
    bit_width: int = Field(..., description="Field width in bits")
    bit_range: str = Field(..., description="Bit range string (e.g., '7:4')")
    mask_hex: str = Field(..., description="Field mask in hex")
    mask: int = Field(..., description="Field mask as integer")
    access: AccessType = Field(AccessType.UNKNOWN, description="Field access type")
    description: str | None = Field(None, description="Field description")
    enumerated_values: list[EnumeratedValueInfo] = Field(
        default_factory=list, 
        description="Enumerated values if defined"
    )
    canonical_path: str = Field(..., description="Canonical path: FIELD:<peripheral>.<register>.<field>")


class RegisterDetail(BaseModel):
    """Detailed register information."""
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., description="Register name")
    display_name: str = Field(..., description="Name with array index if applicable")
    peripheral: str = Field(..., description="Parent peripheral name")
    address_offset_hex: str = Field(..., description="Offset from peripheral base in hex")
    address_offset: int = Field(..., description="Offset as integer")
    absolute_address_hex: str = Field(..., description="Absolute address in hex")
    absolute_address: int = Field(..., description="Absolute address as integer")
    size_bits: int = Field(32, description="Register size in bits")
    access: AccessType = Field(AccessType.UNKNOWN, description="Access type")
    reset_value_hex: str | None = Field(None, description="Reset value in hex")
    reset_value: int | None = Field(None, description="Reset value as integer")
    reset_mask_hex: str | None = Field(None, description="Reset mask in hex")
    description: str | None = Field(None, description="Full description")
    fields: list[FieldInfo] = Field(default_factory=list, description="Register fields")
    canonical_path: str = Field(..., description="Canonical path")
    is_array: bool = Field(False, description="Whether this is an array register")
    array_index: int | None = Field(None, description="Array index if applicable")
    array_size: int | None = Field(None, description="Array size if applicable")


# ============================================================================
# Field Models
# ============================================================================

class FieldDetail(BaseModel):
    """Detailed field information."""
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., description="Field name")
    register: str = Field(..., description="Parent register name")
    peripheral: str = Field(..., description="Parent peripheral name")
    bit_offset: int = Field(..., description="Bit offset within register")
    bit_width: int = Field(..., description="Field width in bits")
    bit_range: str = Field(..., description="Bit range string")
    mask_hex: str = Field(..., description="Field mask in hex")
    mask: int = Field(..., description="Field mask as integer")
    access: AccessType = Field(AccessType.UNKNOWN, description="Field access type")
    description: str | None = Field(None, description="Field description")
    enumerated_values: list[EnumeratedValueInfo] = Field(
        default_factory=list,
        description="Enumerated values if defined"
    )
    canonical_path: str = Field(..., description="Canonical path")
    modified_write_values: str | None = Field(None, description="Modified write behavior")
    read_action: str | None = Field(None, description="Read action behavior")


# ============================================================================
# Search Models
# ============================================================================

class SearchResult(BaseModel):
    """A single search result."""
    model_config = ConfigDict(populate_by_name=True)
    
    canonical_path: str = Field(..., description="Canonical path to the component")
    component_type: ComponentType = Field(..., description="Type of component")
    name: str = Field(..., description="Component name")
    match_score: float = Field(1.0, description="Relevance score (0-1)")
    snippet: str = Field(..., description="Short description or context")


class SearchResultList(BaseModel):
    """List of search results."""
    model_config = ConfigDict(populate_by_name=True)
    
    query: str = Field(..., description="Original search query")
    kind: str = Field(..., description="Type filter used")
    total_results: int = Field(..., description="Total matching results")
    returned_count: int = Field(..., description="Number of results returned")
    results: list[SearchResult] = Field(default_factory=list, description="Search results")


# ============================================================================
# Resolve Models
# ============================================================================

class ResolvedComponent(BaseModel):
    """A resolved SVD component."""
    model_config = ConfigDict(populate_by_name=True)
    
    canonical_path: str = Field(..., description="Canonical path")
    component_type: ComponentType = Field(..., description="Type of component")
    name: str = Field(..., description="Component name")
    
    # For peripherals
    base_address: int | None = Field(None, description="Base address (peripherals)")
    base_address_hex: str | None = Field(None, description="Base address in hex")
    
    # For registers
    absolute_address: int | None = Field(None, description="Absolute address (registers)")
    absolute_address_hex: str | None = Field(None, description="Absolute address in hex")
    address_offset: int | None = Field(None, description="Offset from peripheral base")
    size_bits: int | None = Field(None, description="Size in bits")
    access: AccessType | None = Field(None, description="Access type")
    reset_value: int | None = Field(None, description="Reset value")
    reset_value_hex: str | None = Field(None, description="Reset value in hex")
    
    # For fields
    bit_offset: int | None = Field(None, description="Bit offset (fields)")
    bit_width: int | None = Field(None, description="Bit width (fields)")
    mask: int | None = Field(None, description="Field mask")
    mask_hex: str | None = Field(None, description="Field mask in hex")
    
    description: str | None = Field(None, description="Component description")


# ============================================================================
# Decode/Encode Models
# ============================================================================

class DecodedField(BaseModel):
    """A decoded field value."""
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., description="Field name")
    bit_range: str = Field(..., description="Bit range")
    raw_value: int = Field(..., description="Raw extracted value")
    raw_value_hex: str = Field(..., description="Raw value in hex")
    enumerated_name: str | None = Field(None, description="Enumeration name if applicable")
    enumerated_description: str | None = Field(None, description="Enumeration description")
    description: str | None = Field(None, description="Field description")


class DecodedRegister(BaseModel):
    """Result of decoding a register value."""
    model_config = ConfigDict(populate_by_name=True)
    
    peripheral: str = Field(..., description="Peripheral name")
    register: str = Field(..., description="Register name")
    input_value: int = Field(..., description="Input value")
    input_value_hex: str = Field(..., description="Input value in hex")
    fields: list[DecodedField] = Field(default_factory=list, description="Decoded fields")
    markdown_summary: str = Field(..., description="Human-readable markdown summary")


class EncodedField(BaseModel):
    """An encoded field contribution."""
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., description="Field name")
    input_value: int | str = Field(..., description="Input value (int or enum name)")
    resolved_value: int = Field(..., description="Resolved numeric value")
    mask: int = Field(..., description="Field mask")
    shifted_value: int = Field(..., description="Value shifted to position")


class EncodedRegister(BaseModel):
    """Result of encoding a register value."""
    model_config = ConfigDict(populate_by_name=True)
    
    peripheral: str = Field(..., description="Peripheral name")
    register: str = Field(..., description="Register name")
    base_value: int = Field(0, description="Starting base value")
    final_value: int = Field(..., description="Final computed value")
    final_value_hex: str = Field(..., description="Final value in hex")
    fields: list[EncodedField] = Field(default_factory=list, description="Field contributions")
    warnings: list[str] = Field(default_factory=list, description="Warnings (out-of-range, etc.)")
    changed_bits: list[str] = Field(default_factory=list, description="Description of changed bits")


# ============================================================================
# Validation Models
# ============================================================================

class ValidationIssue(BaseModel):
    """A validation issue."""
    model_config = ConfigDict(populate_by_name=True)
    
    severity: str = Field(..., description="Severity: error, warning, info")
    component: str | None = Field(None, description="Component path")
    message: str = Field(..., description="Issue description")
    line: int | None = Field(None, description="Line number if available")


class ValidationResult(BaseModel):
    """Result of SVD validation."""
    model_config = ConfigDict(populate_by_name=True)
    
    valid: bool = Field(..., description="Whether SVD is valid")
    issues: list[ValidationIssue] = Field(default_factory=list, description="Validation issues")
    tool_used: str = Field(..., description="Validation tool used (parser/svdconv)")
