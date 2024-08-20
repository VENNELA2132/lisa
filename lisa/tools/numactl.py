import re
from typing import TYPE_CHECKING, Optional, Tuple, Type, cast
from urllib.parse import urlparse

from assertpy.assertpy import assert_that
from retry import retry

from lisa.base_tools import Cat
from lisa.executable import Tool
from lisa.tools.ls import Ls
from lisa.tools.mkdir import Mkdir
from lisa.tools.powershell import PowerShell
from lisa.tools.rm import Rm
from lisa.util import LisaException, LisaTimeoutException, is_valid_url
from lisa.util.process import ExecutableResult

if TYPE_CHECKING:
    from lisa.operating_system import Posix


class Numactl(Tool):
    # Saving '/home/username/lisa_working/20240323/20240323-070329-867/kvp_client'
    # __pattern_path = re.compile(r"([\w\W]*?)Saving.*(‘|')(?P<path>.+?)(’|')")

    __cxl_node=re.compile(r"node (\d+) cpus:\s*$", re.MULTILINE)
    __numa_nodes=re.compile(r"node (\d+) cpus:\s*$", re.MULTILINE)
    __avg_speed=re.compile(r"(\d+\.\d+) MiB/sec")
    __total_time = re.compile(r"total time:\s+(\d+\.\d+)s")
    @property
    def command(self) -> str:
        return "numactl"

    @property
    def can_install(self) -> bool:
        return True

    def install(self) -> bool:
        posix_os: Posix = cast(Posix, self.node.os)
        posix_os.install_packages("numactl")
        return self._check_exists()

    def help(self) -> ExecutableResult:
        return self.run("-H")

    def _run_command(self,command: str) -> ExecutableResult:
        return self.node.execute(f"{command} --version", shell=True)

    def _is_installed(self,command: str) -> bool:
        result = self._run_command(command)
        return result.exit_code == 0

    def get_cxl_node(self) -> int:
        output = self.help()
        match = self.__cxl_node.findall(output.stdout)

        assert_that(len(match),"CXL node is not present").is_greater_than(0)
        return match[0]
    
    def get_numa_nodes(self):
        output=self.help()
        match = self.__numa_nodes.findall(output.stdout)
        assert_that(len(match),"There should be atleast 1 NUMA node").is_greater_than(0)
        return len(match)
    
    def get_sysbench_memory_output(self, 
                            nodeId: int,
                            threads: Optional[str] = None,
                            memory_scope : Optional[str] = None,
                            memory_oper : Optional[str] = None,
                            memory_block_size : Optional[str] = None,
                            memory_access_mode : Optional[str] = None,
                            memory_hugetlb: Optional[str] = None,
                            memory_total_size: Optional[str] = None,
                            ) -> ExecutableResult:
        if not self._is_installed("sysbench"):
            posix_os: Posix = cast(Posix, self.node.os)
            posix_os.install_packages("sysbench")

        cmd=f" --membind {nodeId} sysbench"
        if threads:
            cmd += f" --threads={threads}"
        
        cmd += " memory"
        
        if memory_scope:
            cmd += f" --memory-scope={memory_scope}"
        
        if memory_oper:
            cmd += f" --memory-oper={memory_oper}"

        if memory_block_size:
            cmd += f" --memory-block-size={memory_block_size}"

        if memory_access_mode:
            cmd += f" --memory-access-mode={memory_access_mode}"
        
        if memory_hugetlb:
            cmd += f" --memory-hugetlb={memory_hugetlb}"

        if memory_total_size:
            cmd += f" --memory-total-size={memory_total_size}"

        cmd += " run"

        output = self.run(cmd)
        return output
    
    def get_node_speed(self,
                       output: ExecutableResult) -> float:
        
        match = self.__avg_speed.findall(output.stdout)
        return match[0]
    
    def get_node_time(self,
                      output: ExecutableResult) -> float:
        
        match = self.__total_time.findall(output.stdout)
        return match[0]
    
    
    




