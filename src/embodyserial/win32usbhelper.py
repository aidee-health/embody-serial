import sys
import os

class Win32USBHelper:
    """
    Natively maps Windows COM ports to their true compiled firmware hardware descriptions
    using direct SetupAPI/ConfigManager tree traversal via ctypes.
    
    Modifies the serial.tools.list_ports.comports() ListPortInfo objects in-place
    to overwrite generic Microsoft driver wrappers with the true hardware labels.
    """
    def __init__(self):
        if sys.platform != "win32":
            raise NotImplementedError("Win32SerialDeviceMapper is only supported on Windows platforms.")
        
        import ctypes
        from ctypes import wintypes, POINTER, Structure, c_void_p, create_string_buffer, byref
        
        self.ctypes = ctypes
        self.byref = byref
        self.create_string_buffer = create_string_buffer
        self.wintypes = wintypes
        self.setupapi = ctypes.windll.setupapi
        self.cfgmgr = ctypes.windll.cfgmgr32
        
        # Structures
        class GUID(Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), 
                        ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]
        
        class DEVPROPKEY(Structure):
            _fields_ = [("fmtid", wintypes.BYTE * 16), ("pid", wintypes.ULONG)]
        
        self.SP_DEVINFO_DATA = type("SP_DEVINFO_DATA", (Structure,), {
            "_fields_": [("cbSize", wintypes.DWORD), ("ClassGuid", GUID), 
                         ("DevInst", wintypes.DWORD), ("Reserved", c_void_p)]
        })
        
        # Core Hardware GUID Keys
        self.GUID_DEVCLASS_PORTS = GUID(0x4D36E978, 0xE325, 0x11CE, (0xBF, 0xC1, 0x08, 0x00, 0x2B, 0xE1, 0x03, 0x18))
        
        # Unified PnP Bus Reported Description Key Matrix
        # GUID: {540b947e-8b40-45bc-a8a2-6a0b894cbda2}, PID: 4 (Little-Endian representation)
        BUS_DESC_GUID = (0x7E, 0x94, 0x0B, 0x54, 0x40, 0x8B, 0xBC, 0x45, 0xA8, 0xA2, 0x6A, 0x0B, 0x89, 0x4C, 0xBD, 0xA2)
        self.DEVPKEY_Device_BusReportedDeviceDesc = DEVPROPKEY(BUS_DESC_GUID, 4)
        
        self.DIGCF_PRESENT = 0x00000002
        
        # Function Prototyping
        self.setupapi.SetupDiGetClassDevsW.argtypes = [POINTER(GUID), ctypes.c_wchar_p, wintypes.HWND, wintypes.DWORD]
        self.setupapi.SetupDiGetClassDevsW.restype = c_void_p
        self.setupapi.SetupDiEnumDeviceInfo.argtypes = [c_void_p, wintypes.DWORD, POINTER(self.SP_DEVINFO_DATA)]
        self.setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
        self.setupapi.SetupDiOpenDevRegKey.argtypes = [c_void_p, POINTER(self.SP_DEVINFO_DATA), wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        self.setupapi.SetupDiOpenDevRegKey.restype = wintypes.HANDLE
        self.setupapi.SetupDiDestroyDeviceInfoList.argtypes = [c_void_p]
        self.setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

        self.cfgmgr.CM_Get_Parent.argtypes = [POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.ULONG]
        self.cfgmgr.CM_Get_DevNode_PropertyW.argtypes = [wintypes.DWORD, POINTER(DEVPROPKEY), POINTER(wintypes.ULONG), ctypes.c_char_p, POINTER(wintypes.ULONG), wintypes.ULONG]

    def _get_node_string(self, devinst, propkey):
        prop_type = self.wintypes.ULONG()
        size = self.wintypes.ULONG(0)
        self.cfgmgr.CM_Get_DevNode_PropertyW(devinst, self.byref(propkey), self.byref(prop_type), None, self.byref(size), 0)
        if size.value > 0:
            buffer = self.create_string_buffer(size.value)
            if self.cfgmgr.CM_Get_DevNode_PropertyW(devinst, self.byref(propkey), self.byref(prop_type), buffer, self.byref(size), 0) == 0:
                return buffer.raw.decode("utf-16-le", errors="ignore").rstrip("\x00")
        return ""

    def decorate_ports(self, port_list):
        """
        Takes a list of ListPortInfo objects, fetches true hardware names natively, 
        and updates their attributes in place.
        """
        import winreg
        from ctypes import c_void_p
        
        # Build raw hardware map first
        hardware_map = {}
        h_dev_info = self.setupapi.SetupDiGetClassDevsW(self.byref(self.GUID_DEVCLASS_PORTS), None, None, self.DIGCF_PRESENT)
        if h_dev_info == c_void_p(-1).value or h_dev_info is None:
            return port_list

        try:
            dev_info_data = self.SP_DEVINFO_DATA()
            dev_info_data.cbSize = self.ctypes.sizeof(self.SP_DEVINFO_DATA)
            index = 0
            
            while self.setupapi.SetupDiEnumDeviceInfo(h_dev_info, index, self.byref(dev_info_data)):
                index += 1
                
                h_device_key = self.setupapi.SetupDiOpenDevRegKey(h_dev_info, self.byref(dev_info_data), 1, 0, 1, 0x0001)
                if h_device_key != -1 and h_device_key is not None:
                    try:
                        port_name, _ = winreg.QueryValueEx(h_device_key, "PortName")
                        winreg.CloseKey(h_device_key)
                    except Exception:
                        continue

                    current_node = dev_info_data.DevInst
                    label = self._get_node_string(current_node, self.DEVPKEY_Device_BusReportedDeviceDesc)
                    
                    if not label or label in ["USB", "PCI"]:
                        parent_node = self.wintypes.DWORD()
                        if self.cfgmgr.CM_Get_Parent(self.byref(parent_node), current_node, 0) == 0:
                            label = self._get_node_string(parent_node.value, self.DEVPKEY_Device_BusReportedDeviceDesc)
                            
                            if not label or label in ["USB", "PCI"]:
                                grandparent_node = self.wintypes.DWORD()
                                if self.cfgmgr.CM_Get_Parent(self.byref(grandparent_node), parent_node.value, 0) == 0:
                                    label = self._get_node_string(grandparent_node.value, self.DEVPKEY_Device_BusReportedDeviceDesc)

                    if label and label not in ["USB", "PCI"]:
                        hardware_map[port_name] = label
        finally:
            self.setupapi.SetupDiDestroyDeviceInfoList(h_dev_info)
            
        # Update the provided objects in-place
        for port in port_list:
            if port.device in hardware_map:
                true_label = hardware_map[port.device]
                port.product = true_label

        return port_list