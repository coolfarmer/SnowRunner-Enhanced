"""Execute every V18 fixture assertion in the embedded GumJS native host."""
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
import test_input_agent
from native_host import NativeDevice

with patch.object(test_input_agent.frida, 'get_local_device', side_effect=NativeDevice):
    test_input_agent.main()
