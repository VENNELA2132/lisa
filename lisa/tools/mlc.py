import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Set, Type

from lisa.base_tools.wget import Wget
from lisa.executable import Tool
from lisa.operating_system import Redhat, Suse, Ubuntu
from lisa.tools import Dmesg
from lisa.tools.echo import Echo
from lisa.tools.tar import Tar
from lisa.util import LisaException, find_groups_in_lines
from lisa.util.process import ExecutableResult

from .ln import Ln
from .python import Python

# segment output of lsvmbus -vv
# VMBUS ID  1: Class_ID = {525074dc-8985-46e2-8057-a307dc18a502}
# - [Dynamic Memory]
# \r\n\t
# Device_ID = {1eccfd72-4b41-45ef-b73a-4a6e44c12924}
# \r\n\t
# Sysfs path: /sys/bus/vmbus/devices/1eccfd72-4b41-45ef-b73a-4a6e44c12924
# \r\n\t
# Rel_ID=1, target_cpu=0
# \r\n\r\n
# VMBUS ID  2: Class_ID = {32412632-86cb-44a2-9b5c-50d1417354f5}
# - Synthetic IDE Controller\r\n\t
# Device_ID = {00000000-0000-8899-0000-000000000000}
# \r\n\t
# Sysfs path: /sys/bus/vmbus/devices/00000000-0000-8899-0000-000000000000
# \r\n\t
# Rel_ID=2, target_cpu=0
# \r\n\r\n
class Mlc(Tool):
    
    _mlc_pkg = (
        "https://downloadmirror.intel.com/822971/mlc_v3.11a.tgz"
    )

    @property
    def command(self) -> str:
        return "mlc"


    @property
    def can_install(self) -> bool:
        return True

    def _install_from_src(self) -> None:
        wget_tool = self.node.tools[Wget]
        tar = self.node.tools[Tar]
        ln = self.node.tools[Ln]
        file_path = wget_tool.get(self._mlc_pkg)
        tar.extract(file=file_path,dest_dir=self.node.working_path.joinpath("mlc"))
        if self.node.is_posix:
            ln.create_link(self.node.working_path.joinpath("mlc/Linux/mlc"),"/usr/bin/mlc")
        else:
            ln.create_link(self.node.working_path.joinpath("mlc/Windows/mlc"),"/usr/bin/mlc")

    def install(self) -> bool:
        self._install_from_src()
        return self._check_exists()
    
    def get_mlc_output(self) -> ExecutableResult:
        echo = self.node.tools[Echo]
        echo.write_to_file("4000","/proc/sys/vm/nr_hugepages",sudo=True)

        return self.run()