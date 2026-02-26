"""
Tests for the SVD Store module.

These tests verify SVD loading, parsing, indexing, and lookup functionality.
"""

import os
from pathlib import Path

import pytest

from mcp_cmsis_svd.svd_store import SVDStore, get_store
from mcp_cmsis_svd.model import AccessType, ComponentType


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def minimal_svd_path() -> str:
    """Path to the minimal test SVD file."""
    return str(Path(__file__).parent / "fixtures" / "minimal.svd")


@pytest.fixture
def store() -> SVDStore:
    """Create a fresh SVD store for each test."""
    return SVDStore()


# ============================================================================
# Load Tests
# ============================================================================

class TestLoad:
    """Tests for SVD loading."""
    
    def test_load_valid_svd(self, store: SVDStore, minimal_svd_path: str):
        """Test loading a valid SVD file."""
        result = store.load(minimal_svd_path)
        
        assert result.success
        assert result.device_id is not None
        assert result.device is not None
        assert result.error is None
        
    def test_load_sets_active_device(self, store: SVDStore, minimal_svd_path: str):
        """Test that loading sets the active device."""
        result = store.load(minimal_svd_path)
        
        assert store._active_device_id == result.device_id
        
    def test_load_invalid_path(self, store: SVDStore):
        """Test loading a non-existent file."""
        result = store.load("/nonexistent/path/to/file.svd")
        
        assert not result.success
        assert "File not found" in result.error
        
    def test_load_invalid_extension(self, store: SVDStore, tmp_path: Path):
        """Test loading a file with wrong extension."""
        # Create a temp file with wrong extension
        bad_file = tmp_path / "test.txt"
        bad_file.write_text("not an svd file")
        
        result = store.load(str(bad_file))
        
        assert not result.success
        assert "Invalid file extension" in result.error
        
    def test_load_caches_parsed_device(self, store: SVDStore, minimal_svd_path: str):
        """Test that loading the same file uses cache."""
        result1 = store.load(minimal_svd_path)
        result2 = store.load(minimal_svd_path)
        
        assert result1.device_id == result2.device_id
        # Cache should have been used (same device_id)


# ============================================================================
# Device Summary Tests
# ============================================================================

class TestDeviceSummary:
    """Tests for device summary."""
    
    def test_device_summary(self, store: SVDStore, minimal_svd_path: str):
        """Test device summary content."""
        result = store.load(minimal_svd_path)
        
        assert result.device.name == "TEST_MCUTEST"
        assert result.device.vendor == "TestVendor"
        assert result.device.peripheral_count == 2
        assert result.device.register_count > 0
        assert result.device.field_count > 0
        
    def test_device_cpu_info(self, store: SVDStore, minimal_svd_path: str):
        """Test CPU information in device summary."""
        result = store.load(minimal_svd_path)
        
        assert result.device.cpu_name == "CM4"
        assert result.device.mpu_present is True
        assert result.device.fpu_present is True


# ============================================================================
# Peripheral Tests
# ============================================================================

class TestPeripherals:
    """Tests for peripheral access."""
    
    def test_list_peripherals(self, store: SVDStore, minimal_svd_path: str):
        """Test listing peripherals."""
        store.load(minimal_svd_path)
        
        peripherals = store.list_peripherals()
        
        assert len(peripherals) == 2
        names = [p.name for p in peripherals]
        assert "GPIOA" in names
        assert "TIM2" in names
        
    def test_list_peripherals_with_filter(self, store: SVDStore, minimal_svd_path: str):
        """Test listing peripherals with filter."""
        store.load(minimal_svd_path)
        
        peripherals = store.list_peripherals(filter_str="GPIO")
        
        assert len(peripherals) == 1
        assert peripherals[0].name == "GPIOA"
        
    def test_get_peripheral(self, store: SVDStore, minimal_svd_path: str):
        """Test getting peripheral details."""
        store.load(minimal_svd_path)
        
        periph = store.get_peripheral("GPIOA")
        
        assert periph is not None
        assert periph.name == "GPIOA"
        assert periph.base_address == 0x40020000
        assert periph.base_address_hex == "0x40020000"
        assert periph.register_count == 3
        
    def test_get_peripheral_case_insensitive(self, store: SVDStore, minimal_svd_path: str):
        """Test case-insensitive peripheral lookup."""
        store.load(minimal_svd_path)
        
        periph = store.get_peripheral("gpioa")
        
        assert periph is not None
        assert periph.name == "GPIOA"
        
    def test_get_peripheral_interrupts(self, store: SVDStore, minimal_svd_path: str):
        """Test peripheral interrupt information."""
        store.load(minimal_svd_path)
        
        periph = store.get_peripheral("GPIOA")
        
        assert len(periph.interrupts) == 1
        assert periph.interrupts[0].name == "GPIOA_IRQn"
        assert periph.interrupts[0].value == 10
        
    def test_get_nonexistent_peripheral(self, store: SVDStore, minimal_svd_path: str):
        """Test getting a non-existent peripheral."""
        store.load(minimal_svd_path)
        
        periph = store.get_peripheral("NONEXISTENT")
        
        assert periph is None


# ============================================================================
# Register Tests
# ============================================================================

class TestRegisters:
    """Tests for register access."""
    
    def test_list_registers(self, store: SVDStore, minimal_svd_path: str):
        """Test listing registers for a peripheral."""
        store.load(minimal_svd_path)
        
        registers = store.list_registers("GPIOA")
        
        assert len(registers) == 3
        names = [r.name for r in registers]
        assert "MODER" in names
        assert "OTYPER" in names
        assert "ODR" in names
        
    def test_register_addresses(self, store: SVDStore, minimal_svd_path: str):
        """Test register address calculation."""
        store.load(minimal_svd_path)
        
        registers = store.list_registers("GPIOA")
        moder = next(r for r in registers if r.name == "MODER")
        
        assert moder.address_offset == 0x00
        assert moder.absolute_address == 0x40020000
        
        odr = next(r for r in registers if r.name == "ODR")
        assert odr.address_offset == 0x14
        assert odr.absolute_address == 0x40020014
        
    def test_get_register(self, store: SVDStore, minimal_svd_path: str):
        """Test getting register details."""
        store.load(minimal_svd_path)
        
        reg = store.get_register("GPIOA", "MODER")
        
        assert reg is not None
        assert reg.name == "MODER"
        assert reg.size_bits == 32
        assert reg.access == AccessType.READ_WRITE
        assert reg.reset_value == 0
        
    def test_register_fields(self, store: SVDStore, minimal_svd_path: str):
        """Test register field information."""
        store.load(minimal_svd_path)
        
        reg = store.get_register("GPIOA", "MODER")
        
        assert len(reg.fields) == 2
        mode0 = next(f for f in reg.fields if f.name == "MODE0")
        
        assert mode0.bit_offset == 0
        assert mode0.bit_width == 2
        assert mode0.mask == 0x3
        
    def test_field_enumerated_values(self, store: SVDStore, minimal_svd_path: str):
        """Test field enumerated values."""
        store.load(minimal_svd_path)
        
        reg = store.get_register("GPIOA", "MODER")
        mode0 = next(f for f in reg.fields if f.name == "MODE0")
        
        assert len(mode0.enumerated_values) == 4
        
        # Check enum names
        enum_names = [ev.name for ev in mode0.enumerated_values]
        assert "Input" in enum_names
        assert "Output" in enum_names
        assert "Alternate" in enum_names
        assert "Analog" in enum_names
        
        # Check enum values
        input_enum = next(ev for ev in mode0.enumerated_values if ev.name == "Input")
        assert input_enum.value == 0
        
        output_enum = next(ev for ev in mode0.enumerated_values if ev.name == "Output")
        assert output_enum.value == 1


# ============================================================================
# Field Tests
# ============================================================================

class TestFields:
    """Tests for field access."""
    
    def test_get_field(self, store: SVDStore, minimal_svd_path: str):
        """Test getting field details."""
        store.load(minimal_svd_path)
        
        field = store.get_field("GPIOA", "MODER", "MODE0")
        
        assert field is not None
        assert field.name == "MODE0"
        assert field.bit_offset == 0
        assert field.bit_width == 2
        assert field.mask == 0x3
        assert field.mask_hex == "0x3"
        
    def test_get_field_case_insensitive(self, store: SVDStore, minimal_svd_path: str):
        """Test case-insensitive field lookup."""
        store.load(minimal_svd_path)
        
        field = store.get_field("gpioa", "moder", "mode0")
        
        assert field is not None
        assert field.name == "MODE0"


# ============================================================================
# Search Tests
# ============================================================================

class TestSearch:
    """Tests for search functionality."""
    
    def test_search_peripheral(self, store: SVDStore, minimal_svd_path: str):
        """Test searching for peripherals."""
        store.load(minimal_svd_path)
        
        results = store.search("GPIO")
        
        assert len(results) >= 1
        gpio_result = next((r for r in results if r.name == "GPIOA"), None)
        assert gpio_result is not None
        assert gpio_result.component_type == ComponentType.PERIPHERAL
        
    def test_search_register(self, store: SVDStore, minimal_svd_path: str):
        """Test searching for registers."""
        store.load(minimal_svd_path)
        
        results = store.search("MODER", kind="register")
        
        assert len(results) >= 1
        assert all(r.component_type == ComponentType.REGISTER for r in results)
        
    def test_search_field(self, store: SVDStore, minimal_svd_path: str):
        """Test searching for fields."""
        store.load(minimal_svd_path)
        
        results = store.search("CEN", kind="field")
        
        assert len(results) >= 1
        assert all(r.component_type == ComponentType.FIELD for r in results)
        
    def test_search_any(self, store: SVDStore, minimal_svd_path: str):
        """Test searching across all types."""
        store.load(minimal_svd_path)
        
        results = store.search("TIM", kind="any")
        
        assert len(results) >= 1


# ============================================================================
# Resolve Tests
# ============================================================================

class TestResolve:
    """Tests for path resolution."""
    
    def test_resolve_peripheral_canonical(self, store: SVDStore, minimal_svd_path: str):
        """Test resolving peripheral by canonical path."""
        store.load(minimal_svd_path)
        
        result = store.resolve("PERIPHERAL:GPIOA")
        
        assert result is not None
        assert result.component_type == ComponentType.PERIPHERAL
        assert result.name == "GPIOA"
        assert result.base_address == 0x40020000
        
    def test_resolve_register_canonical(self, store: SVDStore, minimal_svd_path: str):
        """Test resolving register by canonical path."""
        store.load(minimal_svd_path)
        
        result = store.resolve("REG:GPIOA.MODER")
        
        assert result is not None
        assert result.component_type == ComponentType.REGISTER
        assert result.name == "MODER"
        assert result.absolute_address == 0x40020000
        
    def test_resolve_field_canonical(self, store: SVDStore, minimal_svd_path: str):
        """Test resolving field by canonical path."""
        store.load(minimal_svd_path)
        
        result = store.resolve("FIELD:GPIOA.MODER.MODE0")
        
        assert result is not None
        assert result.component_type == ComponentType.FIELD
        assert result.name == "MODE0"
        assert result.bit_offset == 0
        assert result.bit_width == 2
        
    def test_resolve_dotted_path(self, store: SVDStore, minimal_svd_path: str):
        """Test resolving by dotted path."""
        store.load(minimal_svd_path)
        
        result = store.resolve("GPIOA.MODER")
        
        assert result is not None
        assert result.component_type == ComponentType.REGISTER


# ============================================================================
# Decode/Encode Tests
# ============================================================================

class TestDecodeEncode:
    """Tests for register value decode/encode."""
    
    def test_decode_simple(self, store: SVDStore, minimal_svd_path: str):
        """Test decoding a simple register value."""
        store.load(minimal_svd_path)
        
        # Get TIM2.CR1 register (has CEN, UDIS, URS, ARPE fields)
        reg = store.get_register("TIM2", "CR1")
        
        # Decode value with CEN=1, ARPE=1
        # CEN is bit 0, ARPE is bit 7
        value = 0x81  # CEN=1, ARPE=1
        
        # Manually verify field extraction
        cen_field = next(f for f in reg.fields if f.name == "CEN")
        assert (value & cen_field.mask) >> cen_field.bit_offset == 1
        
    def test_field_mask_calculation(self, store: SVDStore, minimal_svd_path: str):
        """Test field mask calculation."""
        store.load(minimal_svd_path)
        
        reg = store.get_register("GPIOA", "MODER")
        mode0 = next(f for f in reg.fields if f.name == "MODE0")
        mode1 = next(f for f in reg.fields if f.name == "MODE1")
        
        # MODE0: bits [1:0], mask = 0x3
        assert mode0.mask == 0x3
        assert mode0.bit_offset == 0
        assert mode0.bit_width == 2
        
        # MODE1: bits [3:2], mask = 0xC
        assert mode1.mask == 0xC
        assert mode1.bit_offset == 2
        assert mode1.bit_width == 2


# ============================================================================
# Global Store Tests
# ============================================================================

class TestGlobalStore:
    """Tests for global store instance."""
    
    def test_get_store_singleton(self):
        """Test that get_store returns a singleton."""
        store1 = get_store()
        store2 = get_store()
        
        assert store1 is store2


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_no_device_loaded(self, store: SVDStore):
        """Test operations with no device loaded."""
        peripherals = store.list_peripherals()
        assert peripherals == []
        
        periph = store.get_peripheral("GPIOA")
        assert periph is None
        
    def test_pagination(self, store: SVDStore, minimal_svd_path: str):
        """Test pagination in list operations."""
        store.load(minimal_svd_path)
        
        # Get first page
        page1 = store.list_peripherals(limit=1, offset=0)
        assert len(page1) == 1
        
        # Get second page
        page2 = store.list_peripherals(limit=1, offset=1)
        assert len(page2) == 1
        
        # Pages should be different
        assert page1[0].name != page2[0].name
