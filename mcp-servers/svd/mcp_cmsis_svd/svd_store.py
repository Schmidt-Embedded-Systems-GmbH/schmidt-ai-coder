"""
SVD Store - Loading, caching, and indexing of CMSIS-SVD files.

This module provides:
- SVD file loading and parsing using cmsis-svd package
- LRU caching for parsed devices
- Fast lookup indexes for peripherals, registers, and fields
- Session state management for active device
"""

import hashlib
import os
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from mcp_cmsis_svd.model import (
    AccessType,
    ComponentType,
    DeviceSummary,
    DeviceLoadResult,
    PeripheralListItem,
    PeripheralDetail,
    RegisterListItem,
    RegisterDetail,
    FieldInfo,
    FieldDetail,
    InterruptInfo,
    EnumeratedValueInfo,
    SearchResult,
    ResolvedComponent,
)

# Try to import cmsis_svd, fall back to internal parser if not available
try:
    from cmsis_svd.parser import SVDParser
    HAS_CMSIS_SVD = True
except ImportError:
    HAS_CMSIS_SVD = False


# ============================================================================
# Constants
# ============================================================================

MAX_CACHE_SIZE = 16  # Maximum number of cached SVD files
MAX_DESCRIPTION_LENGTH = 200  # Truncate descriptions in lists
MAX_SEARCH_RESULTS = 50  # Maximum search results to return


# ============================================================================
# Access Type Mapping
# ============================================================================

def _parse_access(access_val: Any) -> AccessType:
    """Parse SVD access value (string or enum) to AccessType enum."""
    if not access_val:
        return AccessType.UNKNOWN
    
    # Handle enum from cmsis-svd library (e.g., SVDAccessType.READ_WRITE)
    if hasattr(access_val, 'value'):
        # It's an enum, get its string value
        access_str = access_val.value
    else:
        access_str = str(access_val)
    
    access_map = {
        "read-only": AccessType.READ_ONLY,
        "write-only": AccessType.WRITE_ONLY,
        "read-write": AccessType.READ_WRITE,
        "readWrite": AccessType.READ_WRITE,
        "readOnly": AccessType.READ_ONLY,
        "writeOnly": AccessType.WRITE_ONLY,
        "read-writeOnce": AccessType.READ_WRITE_ONCE,
        "writeOnce": AccessType.WRITE_ONCE,
    }
    return access_map.get(access_str, AccessType.UNKNOWN)


# ============================================================================
# SVD Cache
# ============================================================================

@dataclass
class CachedDevice:
    """Cached parsed SVD device with indexes."""
    device_id: str
    path: str
    mtime: float
    summary: DeviceSummary
    raw_device: Any  # The parsed device object from cmsis_svd
    # Indexes for fast lookup
    peripheral_index: dict[str, Any] = field(default_factory=dict)
    register_index: dict[tuple[str, str], Any] = field(default_factory=dict)
    field_index: dict[tuple[str, str, str], Any] = field(default_factory=dict)
    path_index: dict[str, Any] = field(default_factory=dict)  # canonical_path -> object
    name_lower_index: dict[str, str] = field(default_factory=dict)  # lowercase name -> canonical path


class SVDStore:
    """
    Manages SVD file loading, caching, and indexing.
    
    Uses LRU cache to avoid re-parsing large SVD files.
    Maintains indexes for O(1) lookup by name or canonical path.
    """
    
    def __init__(self, max_cache_size: int = MAX_CACHE_SIZE):
        self._cache: OrderedDict[str, CachedDevice] = OrderedDict()
        self._max_cache_size = max_cache_size
        self._active_device_id: str | None = None
    
    def _get_cache_key(self, path: str) -> str:
        """Generate cache key from path and modification time."""
        abs_path = os.path.abspath(path)
        mtime = os.path.getmtime(abs_path)
        return f"{abs_path}:{mtime}"
    
    def _compute_device_id(self, path: str) -> str:
        """Compute unique device ID from file path."""
        abs_path = os.path.abspath(path)
        # Use hash of path for device ID
        return hashlib.sha256(abs_path.encode()).hexdigest()[:16]
    
    def load(self, path: str, strict: bool = False) -> DeviceLoadResult:
        """
        Load and parse an SVD file.
        
        Args:
            path: Path to the SVD file
            strict: Enable strict parsing mode
            
        Returns:
            DeviceLoadResult with device summary or error
        """
        # Validate path
        if not path:
            return DeviceLoadResult(
                success=False,
                error="Path is required"
            )
        
        abs_path = os.path.abspath(path)
        
        if not os.path.exists(abs_path):
            return DeviceLoadResult(
                success=False,
                error=f"File not found: {path}"
            )
        
        if not abs_path.lower().endswith('.svd'):
            # Also accept .xml files
            if not abs_path.lower().endswith('.xml'):
                return DeviceLoadResult(
                    success=False,
                    error=f"Invalid file extension. Expected .svd or .xml, got: {path}"
                )
        
        # Check cache
        cache_key = self._get_cache_key(abs_path)
        if cache_key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(cache_key)
            cached = self._cache[cache_key]
            self._active_device_id = cached.device_id
            return DeviceLoadResult(
                success=True,
                device_id=cached.device_id,
                device=cached.summary
            )
        
        # Parse the SVD file
        try:
            if HAS_CMSIS_SVD:
                device = self._parse_with_cmsis_svd(abs_path, strict)
            else:
                device = self._parse_with_stdlib(abs_path, strict)
        except Exception as e:
            return DeviceLoadResult(
                success=False,
                error=f"Failed to parse SVD: {str(e)}"
            )
        
        if device is None:
            return DeviceLoadResult(
                success=False,
                error="Failed to parse SVD file"
            )
        
        # Build indexes
        device_id = self._compute_device_id(abs_path)
        cached = self._build_indexes(device_id, abs_path, device)
        
        # Add to cache (evict oldest if full)
        if len(self._cache) >= self._max_cache_size:
            self._cache.popitem(last=False)
        
        self._cache[cache_key] = cached
        self._active_device_id = device_id
        
        return DeviceLoadResult(
            success=True,
            device_id=device_id,
            device=cached.summary
        )
    
    def _parse_with_cmsis_svd(self, path: str, strict: bool) -> Any:
        """Parse SVD using cmsis-svd package."""
        parser = SVDParser.for_xml_file(path)
        return parser.get_device()
    
    def _parse_with_stdlib(self, path: str, strict: bool) -> Any:
        """Fallback parser using stdlib ElementTree."""
        # This is a simplified parser for when cmsis-svd is not available
        # It creates a dict-based structure that mimics the cmsis-svd objects
        tree = ET.parse(path)
        root = tree.getroot()
        return self._xml_to_dict(root)
    
    def _xml_to_dict(self, elem: ET.Element) -> dict:
        """Convert XML element to dictionary."""
        result = {}
        for child in elem:
            if len(child) > 0:
                result[child.tag] = self._xml_to_dict(child)
            else:
                result[child.tag] = child.text
        return result
    
    def _build_indexes(self, device_id: str, path: str, device: Any) -> CachedDevice:
        """Build lookup indexes for a device."""
        summary = self._create_summary(device_id, device)
        cached = CachedDevice(
            device_id=device_id,
            path=path,
            mtime=os.path.getmtime(path),
            summary=summary,
            raw_device=device,
        )
        
        # Build indexes
        if HAS_CMSIS_SVD:
            self._index_cmsis_device(cached, device)
        else:
            self._index_dict_device(cached, device)
        
        return cached
    
    def _create_summary(self, device_id: str, device: Any) -> DeviceSummary:
        """Create device summary from parsed device."""
        if HAS_CMSIS_SVD:
            return self._create_summary_cmsis(device_id, device)
        else:
            return self._create_summary_dict(device_id, device)
    
    def _create_summary_cmsis(self, device_id: str, device: Any) -> DeviceSummary:
        """Create summary from cmsis-svd device object."""
        cpu = device.cpu
        peripherals = device.peripherals
        
        register_count = 0
        field_count = 0
        
        for periph in peripherals:
            for reg in periph.registers:
                register_count += 1
                for f in reg.fields:
                    field_count += 1
        
        return DeviceSummary(
            device_id=device_id,
            name=device.name or "Unknown",
            vendor=getattr(device, 'vendor', None),
            description=self._truncate(getattr(device, 'description', None)),
            cpu_name=getattr(cpu, 'name', None) if cpu else None,
            cpu_revision=getattr(cpu, 'revision', None) if cpu else None,
            endian=getattr(cpu, 'endian', None) if cpu else None,
            mpu_present=getattr(cpu, 'mpu_present', None) if cpu else None,
            fpu_present=getattr(cpu, 'fpu_present', None) if cpu else None,
            nvic_priority_bits=getattr(cpu, 'nvic_priority_bits', None) if cpu else None,
            vendor_systick_config=getattr(cpu, 'vendor_systick_config', None) if cpu else None,
            peripheral_count=len(peripherals),
            register_count=register_count,
            field_count=field_count,
            address_unit_bits=getattr(device, 'address_unit_bits', 8),
        )
    
    def _create_summary_dict(self, device_id: str, device: dict) -> DeviceSummary:
        """Create summary from dict-based device."""
        name = device.get('name', 'Unknown')
        cpu = device.get('cpu', {})
        peripherals = device.get('peripherals', {}).get('peripheral', [])
        
        if isinstance(peripherals, dict):
            peripherals = [peripherals]
        
        register_count = 0
        field_count = 0
        
        for periph in peripherals:
            regs = periph.get('registers', {}).get('register', [])
            if isinstance(regs, dict):
                regs = [regs]
            for reg in regs:
                register_count += 1
                fields = reg.get('fields', {}).get('field', [])
                if isinstance(fields, dict):
                    fields = [fields]
                field_count += len(fields)
        
        return DeviceSummary(
            device_id=device_id,
            name=name,
            vendor=device.get('vendor'),
            description=self._truncate(device.get('description')),
            cpu_name=cpu.get('name') if cpu else None,
            peripheral_count=len(peripherals),
            register_count=register_count,
            field_count=field_count,
        )
    
    def _index_cmsis_device(self, cached: CachedDevice, device: Any) -> None:
        """Build indexes from cmsis-svd device object."""
        for periph in device.peripherals:
            periph_name = periph.name
            canonical = f"PERIPHERAL:{periph_name}"
            
            cached.peripheral_index[periph_name] = periph
            cached.path_index[canonical] = periph
            cached.name_lower_index[periph_name.lower()] = canonical
            
            # Index registers
            for reg in periph.registers:
                reg_name = reg.name
                # Handle array registers
                reg_display = reg_name
                if hasattr(reg, 'dim') and reg.dim:
                    # This is an array register - index each element
                    dim = int(reg.dim)
                    dim_index = getattr(reg, 'dim_index', None)
                    for i in range(dim):
                        if dim_index and i < len(dim_index):
                            idx_name = dim_index[i]
                        else:
                            idx_name = str(i)
                        arr_reg_name = f"{reg_name}[{idx_name}]"
                        reg_canonical = f"REG:{periph_name}.{arr_reg_name}"
                        cached.register_index[(periph_name, arr_reg_name)] = reg
                        cached.path_index[reg_canonical] = reg
                        cached.name_lower_index[arr_reg_name.lower()] = reg_canonical
                else:
                    reg_canonical = f"REG:{periph_name}.{reg_name}"
                    cached.register_index[(periph_name, reg_name)] = reg
                    cached.path_index[reg_canonical] = reg
                    cached.name_lower_index[reg_name.lower()] = reg_canonical
                
                # Index fields
                for f in reg.fields:
                    field_name = f.name
                    field_canonical = f"FIELD:{periph_name}.{reg_name}.{field_name}"
                    cached.field_index[(periph_name, reg_name, field_name)] = f
                    cached.path_index[field_canonical] = f
                    cached.name_lower_index[field_name.lower()] = field_canonical
    
    def _index_dict_device(self, cached: CachedDevice, device: dict) -> None:
        """Build indexes from dict-based device."""
        peripherals = device.get('peripherals', {}).get('peripheral', [])
        if isinstance(peripherals, dict):
            peripherals = [peripherals]
        
        for periph in peripherals:
            periph_name = periph.get('name', '')
            canonical = f"PERIPHERAL:{periph_name}"
            
            cached.peripheral_index[periph_name] = periph
            cached.path_index[canonical] = periph
            cached.name_lower_index[periph_name.lower()] = canonical
            
            # Index registers
            regs = periph.get('registers', {}).get('register', [])
            if isinstance(regs, dict):
                regs = [regs]
            
            for reg in regs:
                reg_name = reg.get('name', '')
                reg_canonical = f"REG:{periph_name}.{reg_name}"
                cached.register_index[(periph_name, reg_name)] = reg
                cached.path_index[reg_canonical] = reg
                cached.name_lower_index[reg_name.lower()] = reg_canonical
                
                # Index fields
                fields = reg.get('fields', {}).get('field', [])
                if isinstance(fields, dict):
                    fields = [fields]
                
                for f in fields:
                    field_name = f.get('name', '')
                    field_canonical = f"FIELD:{periph_name}.{reg_name}.{field_name}"
                    cached.field_index[(periph_name, reg_name, field_name)] = f
                    cached.path_index[field_canonical] = f
                    cached.name_lower_index[field_name.lower()] = field_canonical
    
    def _truncate(self, text: str | None, max_len: int = MAX_DESCRIPTION_LENGTH) -> str | None:
        """Truncate text to max length."""
        if not text:
            return None
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."
    
    # ========================================================================
    # Device Access
    # ========================================================================
    
    def get_active_device(self) -> CachedDevice | None:
        """Get the currently active device."""
        if not self._active_device_id:
            return None
        
        for cached in self._cache.values():
            if cached.device_id == self._active_device_id:
                return cached
        return None
    
    def get_device(self, device_id: str | None = None) -> CachedDevice | None:
        """Get device by ID, or active device if not specified."""
        if device_id:
            for cached in self._cache.values():
                if cached.device_id == device_id:
                    return cached
            return None
        return self.get_active_device()
    
    def set_active_device(self, device_id: str) -> bool:
        """Set the active device by ID."""
        for cached in self._cache.values():
            if cached.device_id == device_id:
                self._active_device_id = device_id
                return True
        return False
    
    # ========================================================================
    # Peripheral Access
    # ========================================================================
    
    def list_peripherals(
        self,
        device_id: str | None = None,
        filter_str: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PeripheralListItem]:
        """List peripherals with optional filtering."""
        cached = self.get_device(device_id)
        if not cached:
            return []
        
        results = []
        for name, periph in cached.peripheral_index.items():
            if filter_str and filter_str.lower() not in name.lower():
                continue
            
            if HAS_CMSIS_SVD:
                item = self._periph_to_list_item_cmsis(periph)
            else:
                item = self._periph_to_list_item_dict(periph)
            
            results.append(item)
        
        # Sort by name
        results.sort(key=lambda x: x.name)
        
        # Apply pagination
        return results[offset:offset + limit]
    
    def _periph_to_list_item_cmsis(self, periph: Any) -> PeripheralListItem:
        """Convert cmsis-svd peripheral to list item."""
        return PeripheralListItem(
            name=periph.name,
            base_address_hex=f"0x{periph.base_address:08X}",
            base_address=periph.base_address,
            description=self._truncate(getattr(periph, 'description', None)),
            group_name=getattr(periph, 'group_name', None),
            derived_from=getattr(periph, 'derived_from', None),
            canonical_path=f"PERIPHERAL:{periph.name}",
        )
    
    def _periph_to_list_item_dict(self, periph: dict) -> PeripheralListItem:
        """Convert dict peripheral to list item."""
        base_addr = int(periph.get('baseAddress', '0'), 0) if isinstance(periph.get('baseAddress'), str) else periph.get('baseAddress', 0)
        return PeripheralListItem(
            name=periph.get('name', ''),
            base_address_hex=f"0x{base_addr:08X}",
            base_address=base_addr,
            description=self._truncate(periph.get('description')),
            group_name=periph.get('groupName'),
            derived_from=periph.get('derivedFrom'),
            canonical_path=f"PERIPHERAL:{periph.get('name', '')}",
        )
    
    def get_peripheral(
        self,
        peripheral: str,
        device_id: str | None = None,
    ) -> PeripheralDetail | None:
        """Get detailed peripheral information."""
        cached = self.get_device(device_id)
        if not cached:
            return None
        
        periph = cached.peripheral_index.get(peripheral)
        if not periph:
            # Try case-insensitive lookup
            canonical = cached.name_lower_index.get(peripheral.lower(), '')
            if canonical.startswith('PERIPHERAL:'):
                periph = cached.path_index.get(canonical)
        
        if not periph:
            return None
        
        if HAS_CMSIS_SVD:
            return self._periph_to_detail_cmsis(periph)
        else:
            return self._periph_to_detail_dict(periph)
    
    def _periph_to_detail_cmsis(self, periph: Any) -> PeripheralDetail:
        """Convert cmsis-svd peripheral to detail."""
        interrupts = []
        for intr in getattr(periph, 'interrupts', []):
            interrupts.append(InterruptInfo(
                name=intr.name,
                value=intr.value,
                description=getattr(intr, 'description', None),
            ))
        
        registers = getattr(periph, 'registers', [])
        key_regs = [r.name for r in registers[:5]] if registers else []
        
        return PeripheralDetail(
            name=periph.name,
            base_address_hex=f"0x{periph.base_address:08X}",
            base_address=periph.base_address,
            description=getattr(periph, 'description', None),
            group_name=getattr(periph, 'group_name', None),
            version=getattr(periph, 'version', None),
            derived_from=getattr(periph, 'derived_from', None),
            register_count=len(registers),
            cluster_count=len(getattr(periph, 'clusters', [])),
            interrupts=interrupts,
            key_registers=key_regs,
            canonical_path=f"PERIPHERAL:{periph.name}",
        )
    
    def _periph_to_detail_dict(self, periph: dict) -> PeripheralDetail:
        """Convert dict peripheral to detail."""
        base_addr = int(periph.get('baseAddress', '0'), 0) if isinstance(periph.get('baseAddress'), str) else periph.get('baseAddress', 0)
        
        interrupts = []
        intrs = periph.get('interrupt', [])
        if isinstance(intrs, dict):
            intrs = [intrs]
        for intr in intrs:
            interrupts.append(InterruptInfo(
                name=intr.get('name', ''),
                value=int(intr.get('value', 0)),
                description=intr.get('description'),
            ))
        
        regs = periph.get('registers', {}).get('register', [])
        if isinstance(regs, dict):
            regs = [regs]
        key_regs = [r.get('name', '') for r in regs[:5]] if regs else []
        
        return PeripheralDetail(
            name=periph.get('name', ''),
            base_address_hex=f"0x{base_addr:08X}",
            base_address=base_addr,
            description=periph.get('description'),
            group_name=periph.get('groupName'),
            version=periph.get('version'),
            derived_from=periph.get('derivedFrom'),
            register_count=len(regs),
            interrupts=interrupts,
            key_registers=key_regs,
            canonical_path=f"PERIPHERAL:{periph.get('name', '')}",
        )
    
    # ========================================================================
    # Register Access
    # ========================================================================
    
    def list_registers(
        self,
        peripheral: str,
        device_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RegisterListItem]:
        """List registers for a peripheral."""
        cached = self.get_device(device_id)
        if not cached:
            return []
        
        periph = cached.peripheral_index.get(peripheral)
        if not periph:
            return []
        
        results = []
        
        if HAS_CMSIS_SVD:
            base_addr = periph.base_address
            for reg in getattr(periph, 'registers', []):
                # Handle array registers
                if hasattr(reg, 'dim') and reg.dim:
                    dim = int(reg.dim)
                    dim_index = getattr(reg, 'dim_index', None)
                    dim_increment = int(getattr(reg, 'dim_increment', 0))
                    
                    for i in range(dim):
                        if dim_index and i < len(dim_index):
                            idx_name = dim_index[i]
                        else:
                            idx_name = str(i)
                        
                        arr_offset = i * dim_increment
                        item = self._reg_to_list_item_cmsis(
                            reg, base_addr, 
                            display_name=f"{reg.name}[{idx_name}]",
                            offset_override=arr_offset
                        )
                        results.append(item)
                else:
                    item = self._reg_to_list_item_cmsis(reg, base_addr)
                    results.append(item)
        else:
            base_addr = int(periph.get('baseAddress', '0'), 0) if isinstance(periph.get('baseAddress'), str) else periph.get('baseAddress', 0)
            regs = periph.get('registers', {}).get('register', [])
            if isinstance(regs, dict):
                regs = [regs]
            for reg in regs:
                item = self._reg_to_list_item_dict(reg, base_addr, peripheral)
                results.append(item)
        
        # Sort by offset
        results.sort(key=lambda x: x.address_offset)
        
        return results[offset:offset + limit]
    
    def _reg_to_list_item_cmsis(
        self, 
        reg: Any, 
        base_addr: int,
        display_name: str | None = None,
        offset_override: int | None = None,
    ) -> RegisterListItem:
        """Convert cmsis-svd register to list item."""
        offset = offset_override if offset_override is not None else reg.address_offset
        abs_addr = base_addr + offset
        
        return RegisterListItem(
            name=reg.name,
            display_name=display_name or reg.name,
            address_offset_hex=f"0x{offset:04X}",
            address_offset=offset,
            absolute_address_hex=f"0x{abs_addr:08X}",
            absolute_address=abs_addr,
            size_bits=getattr(reg, 'size', 32) or 32,
            access=_parse_access(getattr(reg, 'access', None)),
            reset_value_hex=f"0x{reg.reset_value:X}" if hasattr(reg, 'reset_value') and reg.reset_value is not None else None,
            description=self._truncate(getattr(reg, 'description', None)),
            canonical_path=f"REG:{reg.name}",  # Will be updated by caller
        )
    
    def _reg_to_list_item_dict(self, reg: dict, base_addr: int, peripheral: str) -> RegisterListItem:
        """Convert dict register to list item."""
        offset_str = reg.get('addressOffset', '0')
        offset = int(offset_str, 0) if isinstance(offset_str, str) else offset_str
        abs_addr = base_addr + offset
        
        reset_val = reg.get('resetValue')
        if reset_val:
            reset_val = int(reset_val, 0) if isinstance(reset_val, str) else reset_val
        
        return RegisterListItem(
            name=reg.get('name', ''),
            display_name=reg.get('name', ''),
            address_offset_hex=f"0x{offset:04X}",
            address_offset=offset,
            absolute_address_hex=f"0x{abs_addr:08X}",
            absolute_address=abs_addr,
            size_bits=int(reg.get('size', 32)) if reg.get('size') else 32,
            access=_parse_access(reg.get('access')),
            reset_value_hex=f"0x{reset_val:X}" if reset_val is not None else None,
            description=self._truncate(reg.get('description')),
            canonical_path=f"REG:{peripheral}.{reg.get('name', '')}",
        )
    
    def get_register(
        self,
        peripheral: str,
        register: str,
        device_id: str | None = None,
    ) -> RegisterDetail | None:
        """Get detailed register information."""
        cached = self.get_device(device_id)
        if not cached:
            return None
        
        # Look up register
        reg = cached.register_index.get((peripheral, register))
        if not reg:
            # Try case-insensitive
            for (p, r), obj in cached.register_index.items():
                if p.lower() == peripheral.lower() and r.lower() == register.lower():
                    reg = obj
                    peripheral = p
                    register = r
                    break
        
        if not reg:
            return None
        
        periph = cached.peripheral_index.get(peripheral)
        if not periph:
            return None
        
        if HAS_CMSIS_SVD:
            return self._reg_to_detail_cmsis(reg, periph, register)
        else:
            return self._reg_to_detail_dict(reg, periph, peripheral, register)
    
    def _reg_to_detail_cmsis(self, reg: Any, periph: Any, display_name: str) -> RegisterDetail:
        """Convert cmsis-svd register to detail."""
        base_addr = periph.base_address
        offset = reg.address_offset
        abs_addr = base_addr + offset
        
        fields = []
        for f in getattr(reg, 'fields', []):
            field_info = self._field_to_info_cmsis(f, periph.name, reg.name)
            fields.append(field_info)
        
        # Sort fields by bit offset
        fields.sort(key=lambda x: x.bit_offset)
        
        return RegisterDetail(
            name=reg.name,
            display_name=display_name,
            peripheral=periph.name,
            address_offset_hex=f"0x{offset:04X}",
            address_offset=offset,
            absolute_address_hex=f"0x{abs_addr:08X}",
            absolute_address=abs_addr,
            size_bits=getattr(reg, 'size', 32) or 32,
            access=_parse_access(getattr(reg, 'access', None)),
            reset_value_hex=f"0x{reg.reset_value:X}" if hasattr(reg, 'reset_value') and reg.reset_value is not None else None,
            reset_value=reg.reset_value if hasattr(reg, 'reset_value') else None,
            reset_mask_hex=f"0x{reg.reset_mask:X}" if hasattr(reg, 'reset_mask') and reg.reset_mask is not None else None,
            description=getattr(reg, 'description', None),
            fields=fields,
            canonical_path=f"REG:{periph.name}.{display_name}",
            is_array=hasattr(reg, 'dim') and reg.dim is not None,
        )
    
    def _reg_to_detail_dict(self, reg: dict, periph: dict, peripheral: str, display_name: str) -> RegisterDetail:
        """Convert dict register to detail."""
        base_addr = int(periph.get('baseAddress', '0'), 0) if isinstance(periph.get('baseAddress'), str) else periph.get('baseAddress', 0)
        offset_str = reg.get('addressOffset', '0')
        offset = int(offset_str, 0) if isinstance(offset_str, str) else offset_str
        abs_addr = base_addr + offset
        
        reset_val = reg.get('resetValue')
        if reset_val:
            reset_val = int(reset_val, 0) if isinstance(reset_val, str) else reset_val
        
        fields = []
        flds = reg.get('fields', {}).get('field', [])
        if isinstance(flds, dict):
            flds = [flds]
        for f in flds:
            field_info = self._field_to_info_dict(f, peripheral, reg.get('name', ''))
            fields.append(field_info)
        
        fields.sort(key=lambda x: x.bit_offset)
        
        return RegisterDetail(
            name=reg.get('name', ''),
            display_name=display_name,
            peripheral=peripheral,
            address_offset_hex=f"0x{offset:04X}",
            address_offset=offset,
            absolute_address_hex=f"0x{abs_addr:08X}",
            absolute_address=abs_addr,
            size_bits=int(reg.get('size', 32)) if reg.get('size') else 32,
            access=_parse_access(reg.get('access')),
            reset_value_hex=f"0x{reset_val:X}" if reset_val is not None else None,
            reset_value=reset_val,
            description=reg.get('description'),
            fields=fields,
            canonical_path=f"REG:{peripheral}.{display_name}",
        )
    
    # ========================================================================
    # Field Access
    # ========================================================================
    
    def _field_to_info_cmsis(self, f: Any, peripheral: str, register: str) -> FieldInfo:
        """Convert cmsis-svd field to FieldInfo."""
        bit_offset = f.bit_offset
        bit_width = f.bit_width
        mask = ((1 << bit_width) - 1) << bit_offset
        
        enumerated = []
        if hasattr(f, 'enumerated_values') and f.enumerated_values:
            # f.enumerated_values is a list of SVDEnumeratedValues objects
            # Each SVDEnumeratedValues has an enumerated_values attribute with SVDEnumeratedValue objects
            for ev_container in f.enumerated_values:
                if hasattr(ev_container, 'enumerated_values') and ev_container.enumerated_values:
                    for ev in ev_container.enumerated_values:
                        enumerated.append(EnumeratedValueInfo(
                            name=ev.name,
                            value=ev.value,
                            value_hex=f"0x{ev.value:X}",
                            description=getattr(ev, 'description', None),
                        ))
        
        return FieldInfo(
            name=f.name,
            bit_offset=bit_offset,
            bit_width=bit_width,
            bit_range=f"{bit_offset + bit_width - 1}:{bit_offset}" if bit_width > 1 else str(bit_offset),
            mask_hex=f"0x{mask:X}",
            mask=mask,
            access=_parse_access(getattr(f, 'access', None)),
            description=getattr(f, 'description', None),
            enumerated_values=enumerated,
            canonical_path=f"FIELD:{peripheral}.{register}.{f.name}",
        )
    
    def _field_to_info_dict(self, f: dict, peripheral: str, register: str) -> FieldInfo:
        """Convert dict field to FieldInfo."""
        bit_offset = int(f.get('bitOffset', 0))
        bit_width = int(f.get('bitWidth', 1))
        mask = ((1 << bit_width) - 1) << bit_offset
        
        enumerated = []
        evs = f.get('enumeratedValues', {}).get('enumeratedValue', [])
        if isinstance(evs, dict):
            evs = [evs]
        for ev in evs:
            val = ev.get('value', 0)
            if isinstance(val, str):
                val = int(val, 0)
            enumerated.append(EnumeratedValueInfo(
                name=ev.get('name', ''),
                value=val,
                value_hex=f"0x{val:X}",
                description=ev.get('description'),
            ))
        
        return FieldInfo(
            name=f.get('name', ''),
            bit_offset=bit_offset,
            bit_width=bit_width,
            bit_range=f"{bit_offset + bit_width - 1}:{bit_offset}" if bit_width > 1 else str(bit_offset),
            mask_hex=f"0x{mask:X}",
            mask=mask,
            access=_parse_access(f.get('access')),
            description=f.get('description'),
            enumerated_values=enumerated,
            canonical_path=f"FIELD:{peripheral}.{register}.{f.get('name', '')}",
        )
    
    def get_field(
        self,
        peripheral: str,
        register: str,
        field: str,
        device_id: str | None = None,
    ) -> FieldDetail | None:
        """Get detailed field information."""
        cached = self.get_device(device_id)
        if not cached:
            return None
        
        # Look up field
        f = cached.field_index.get((peripheral, register, field))
        if not f:
            # Try case-insensitive
            for (p, r, fld), obj in cached.field_index.items():
                if (p.lower() == peripheral.lower() and 
                    r.lower() == register.lower() and 
                    fld.lower() == field.lower()):
                    f = obj
                    peripheral = p
                    register = r
                    field = fld
                    break
        
        if not f:
            return None
        
        if HAS_CMSIS_SVD:
            return self._field_to_detail_cmsis(f, peripheral, register)
        else:
            return self._field_to_detail_dict(f, peripheral, register)
    
    def _field_to_detail_cmsis(self, f: Any, peripheral: str, register: str) -> FieldDetail:
        """Convert cmsis-svd field to FieldDetail."""
        bit_offset = f.bit_offset
        bit_width = f.bit_width
        mask = ((1 << bit_width) - 1) << bit_offset
        
        enumerated = []
        if hasattr(f, 'enumerated_values') and f.enumerated_values:
            # f.enumerated_values is a list of SVDEnumeratedValues objects
            # Each SVDEnumeratedValues has an enumerated_values attribute with SVDEnumeratedValue objects
            for ev_container in f.enumerated_values:
                if hasattr(ev_container, 'enumerated_values') and ev_container.enumerated_values:
                    for ev in ev_container.enumerated_values:
                        enumerated.append(EnumeratedValueInfo(
                            name=ev.name,
                            value=ev.value,
                            value_hex=f"0x{ev.value:X}",
                            description=getattr(ev, 'description', None),
                        ))
        
        return FieldDetail(
            name=f.name,
            register=register,
            peripheral=peripheral,
            bit_offset=bit_offset,
            bit_width=bit_width,
            bit_range=f"{bit_offset + bit_width - 1}:{bit_offset}" if bit_width > 1 else str(bit_offset),
            mask_hex=f"0x{mask:X}",
            mask=mask,
            access=_parse_access(getattr(f, 'access', None)),
            description=getattr(f, 'description', None),
            enumerated_values=enumerated,
            canonical_path=f"FIELD:{peripheral}.{register}.{f.name}",
            modified_write_values=getattr(f, 'modified_write_values', None),
            read_action=getattr(f, 'read_action', None),
        )
    
    def _field_to_detail_dict(self, f: dict, peripheral: str, register: str) -> FieldDetail:
        """Convert dict field to FieldDetail."""
        bit_offset = int(f.get('bitOffset', 0))
        bit_width = int(f.get('bitWidth', 1))
        mask = ((1 << bit_width) - 1) << bit_offset
        
        enumerated = []
        evs = f.get('enumeratedValues', {}).get('enumeratedValue', [])
        if isinstance(evs, dict):
            evs = [evs]
        for ev in evs:
            val = ev.get('value', 0)
            if isinstance(val, str):
                val = int(val, 0)
            enumerated.append(EnumeratedValueInfo(
                name=ev.get('name', ''),
                value=val,
                value_hex=f"0x{val:X}",
                description=ev.get('description'),
            ))
        
        return FieldDetail(
            name=f.get('name', ''),
            register=register,
            peripheral=peripheral,
            bit_offset=bit_offset,
            bit_width=bit_width,
            bit_range=f"{bit_offset + bit_width - 1}:{bit_offset}" if bit_width > 1 else str(bit_offset),
            mask_hex=f"0x{mask:X}",
            mask=mask,
            access=_parse_access(f.get('access')),
            description=f.get('description'),
            enumerated_values=enumerated,
            canonical_path=f"FIELD:{peripheral}.{register}.{f.get('name', '')}",
        )
    
    # ========================================================================
    # Search
    # ========================================================================
    
    def search(
        self,
        query: str,
        kind: str = "any",
        limit: int = 20,
        device_id: str | None = None,
    ) -> list[SearchResult]:
        """Search for components by name or description."""
        cached = self.get_device(device_id)
        if not cached:
            return []
        
        query_lower = query.lower()
        results = []
        
        # Search peripherals
        if kind in ("any", "peripheral"):
            for name, periph in cached.peripheral_index.items():
                score = self._match_score(query_lower, name.lower())
                if score > 0:
                    desc = ""
                    if HAS_CMSIS_SVD:
                        desc = getattr(periph, 'description', '') or ""
                    else:
                        desc = periph.get('description', '') or ""
                    
                    results.append(SearchResult(
                        canonical_path=f"PERIPHERAL:{name}",
                        component_type=ComponentType.PERIPHERAL,
                        name=name,
                        match_score=score,
                        snippet=self._truncate(desc, 100) or f"Peripheral at 0x{periph.base_address if HAS_CMSIS_SVD else periph.get('baseAddress', '0'):08X}",
                    ))
        
        # Search registers
        if kind in ("any", "register"):
            for (periph, reg_name), reg in cached.register_index.items():
                score = self._match_score(query_lower, reg_name.lower())
                if score > 0:
                    desc = ""
                    if HAS_CMSIS_SVD:
                        desc = getattr(reg, 'description', '') or ""
                    else:
                        desc = reg.get('description', '') or ""
                    
                    results.append(SearchResult(
                        canonical_path=f"REG:{periph}.{reg_name}",
                        component_type=ComponentType.REGISTER,
                        name=reg_name,
                        match_score=score,
                        snippet=self._truncate(desc, 100) or f"Register in {periph}",
                    ))
        
        # Search fields
        if kind in ("any", "field"):
            for (periph, reg_name, field_name), f in cached.field_index.items():
                score = self._match_score(query_lower, field_name.lower())
                if score > 0:
                    desc = ""
                    if HAS_CMSIS_SVD:
                        desc = getattr(f, 'description', '') or ""
                    else:
                        desc = f.get('description', '') or ""
                    
                    results.append(SearchResult(
                        canonical_path=f"FIELD:{periph}.{reg_name}.{field_name}",
                        component_type=ComponentType.FIELD,
                        name=field_name,
                        match_score=score,
                        snippet=self._truncate(desc, 100) or f"Field in {periph}.{reg_name}",
                    ))
        
        # Sort by score (descending) then name
        results.sort(key=lambda x: (-x.match_score, x.name))
        
        return results[:limit]
    
    def _match_score(self, query: str, text: str) -> float:
        """Calculate match score (0-1) for query against text."""
        if query in text:
            # Exact substring match
            if text == query:
                return 1.0
            elif text.startswith(query):
                return 0.9
            else:
                return 0.7
        
        # Simple character matching for fuzzy search
        query_chars = set(query)
        text_chars = set(text)
        common = query_chars & text_chars
        if len(common) < len(query_chars) * 0.5:
            return 0.0
        
        return len(common) / max(len(query_chars), len(text_chars)) * 0.5
    
    # ========================================================================
    # Resolve
    # ========================================================================
    
    def resolve(
        self,
        path: str,
        device_id: str | None = None,
    ) -> ResolvedComponent | None:
        """Resolve a canonical path or dotted path to a component."""
        cached = self.get_device(device_id)
        if not cached:
            return None
        
        # Try canonical path first
        if ':' in path:
            obj = cached.path_index.get(path)
            if obj:
                return self._obj_to_resolved(path, obj, cached)
        
        # Try dotted path (e.g., "GPIOA.ODR")
        parts = path.split('.')
        if len(parts) == 1:
            # Peripheral
            periph = cached.peripheral_index.get(parts[0])
            if periph:
                return self._obj_to_resolved(f"PERIPHERAL:{parts[0]}", periph, cached)
        elif len(parts) == 2:
            # Register
            reg = cached.register_index.get((parts[0], parts[1]))
            if reg:
                return self._obj_to_resolved(f"REG:{parts[0]}.{parts[1]}", reg, cached)
        elif len(parts) == 3:
            # Field
            f = cached.field_index.get((parts[0], parts[1], parts[2]))
            if f:
                return self._obj_to_resolved(f"FIELD:{parts[0]}.{parts[1]}.{parts[2]}", f, cached)
        
        # Try case-insensitive lookup
        canonical = cached.name_lower_index.get(path.lower())
        if canonical:
            obj = cached.path_index.get(canonical)
            if obj:
                return self._obj_to_resolved(canonical, obj, cached)
        
        return None
    
    def _obj_to_resolved(self, canonical: str, obj: Any, cached: CachedDevice) -> ResolvedComponent:
        """Convert object to ResolvedComponent."""
        if canonical.startswith('PERIPHERAL:'):
            if HAS_CMSIS_SVD:
                return ResolvedComponent(
                    canonical_path=canonical,
                    component_type=ComponentType.PERIPHERAL,
                    name=obj.name,
                    base_address=obj.base_address,
                    base_address_hex=f"0x{obj.base_address:08X}",
                    description=getattr(obj, 'description', None),
                )
            else:
                base_addr = int(obj.get('baseAddress', '0'), 0) if isinstance(obj.get('baseAddress'), str) else obj.get('baseAddress', 0)
                return ResolvedComponent(
                    canonical_path=canonical,
                    component_type=ComponentType.PERIPHERAL,
                    name=obj.get('name', ''),
                    base_address=base_addr,
                    base_address_hex=f"0x{base_addr:08X}",
                    description=obj.get('description'),
                )
        
        elif canonical.startswith('REG:'):
            # Extract peripheral name from path
            parts = canonical[4:].split('.')
            periph_name = parts[0] if parts else ''
            periph = cached.peripheral_index.get(periph_name)
            
            if HAS_CMSIS_SVD and periph:
                base_addr = periph.base_address
                offset = obj.address_offset
                abs_addr = base_addr + offset
                
                return ResolvedComponent(
                    canonical_path=canonical,
                    component_type=ComponentType.REGISTER,
                    name=obj.name,
                    absolute_address=abs_addr,
                    absolute_address_hex=f"0x{abs_addr:08X}",
                    address_offset=offset,
                    size_bits=getattr(obj, 'size', 32) or 32,
                    access=_parse_access(getattr(obj, 'access', None)),
                    reset_value=obj.reset_value if hasattr(obj, 'reset_value') else None,
                    reset_value_hex=f"0x{obj.reset_value:X}" if hasattr(obj, 'reset_value') and obj.reset_value is not None else None,
                    description=getattr(obj, 'description', None),
                )
            elif periph:
                base_addr = int(periph.get('baseAddress', '0'), 0) if isinstance(periph.get('baseAddress'), str) else periph.get('baseAddress', 0)
                offset_str = obj.get('addressOffset', '0')
                offset = int(offset_str, 0) if isinstance(offset_str, str) else offset_str
                abs_addr = base_addr + offset
                
                reset_val = obj.get('resetValue')
                if reset_val:
                    reset_val = int(reset_val, 0) if isinstance(reset_val, str) else reset_val
                
                return ResolvedComponent(
                    canonical_path=canonical,
                    component_type=ComponentType.REGISTER,
                    name=obj.get('name', ''),
                    absolute_address=abs_addr,
                    absolute_address_hex=f"0x{abs_addr:08X}",
                    address_offset=offset,
                    size_bits=int(obj.get('size', 32)) if obj.get('size') else 32,
                    access=_parse_access(obj.get('access')),
                    reset_value=reset_val,
                    reset_value_hex=f"0x{reset_val:X}" if reset_val is not None else None,
                    description=obj.get('description'),
                )
        
        elif canonical.startswith('FIELD:'):
            parts = canonical[6:].split('.')
            periph_name = parts[0] if len(parts) > 0 else ''
            reg_name = parts[1] if len(parts) > 1 else ''
            
            if HAS_CMSIS_SVD:
                bit_offset = obj.bit_offset
                bit_width = obj.bit_width
                mask = ((1 << bit_width) - 1) << bit_offset
                
                return ResolvedComponent(
                    canonical_path=canonical,
                    component_type=ComponentType.FIELD,
                    name=obj.name,
                    bit_offset=bit_offset,
                    bit_width=bit_width,
                    mask=mask,
                    mask_hex=f"0x{mask:X}",
                    access=_parse_access(getattr(obj, 'access', None)),
                    description=getattr(obj, 'description', None),
                )
            else:
                bit_offset = int(obj.get('bitOffset', 0))
                bit_width = int(obj.get('bitWidth', 1))
                mask = ((1 << bit_width) - 1) << bit_offset
                
                return ResolvedComponent(
                    canonical_path=canonical,
                    component_type=ComponentType.FIELD,
                    name=obj.get('name', ''),
                    bit_offset=bit_offset,
                    bit_width=bit_width,
                    mask=mask,
                    mask_hex=f"0x{mask:X}",
                    access=_parse_access(obj.get('access')),
                    description=obj.get('description'),
                )
        
        # Fallback
        return ResolvedComponent(
            canonical_path=canonical,
            component_type=ComponentType.PERIPHERAL,
            name=str(obj),
        )


# ============================================================================
# Global Store Instance
# ============================================================================

# Global store for use by the MCP server
_store: SVDStore | None = None


def get_store() -> SVDStore:
    """Get the global SVD store instance."""
    global _store
    if _store is None:
        _store = SVDStore()
    return _store
