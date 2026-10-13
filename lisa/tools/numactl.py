# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import re
from typing import List, Optional, Tuple, cast

from lisa.executable import Tool
from lisa.operating_system import Posix
from lisa.util import LisaException, SkippedException
from lisa.util.process import ExecutableResult


class Numactl(Tool):
    _node_cpus_pattern = re.compile(r"^node (\d+) cpus:(.*)$", re.MULTILINE)
    _average_speed_pattern = re.compile(r"(\d+(?:\.\d+)?) MiB/sec")
    _total_time_pattern = re.compile(r"total time:\s+(\d+(?:\.\d+)?)s")

    @property
    def command(self) -> str:
        return "numactl"

    @property
    def can_install(self) -> bool:
        return True

    def _install(self) -> bool:
        posix_os = cast(Posix, self.node.os)
        posix_os.install_packages("numactl")
        return self._check_exists()

    def get_cxl_node(self) -> int:
        cxl_nodes, _ = self._get_memory_nodes()
        if not cxl_nodes:
            raise SkippedException("No CPU-less CXL memory node is present")
        if len(cxl_nodes) > 1:
            raise LisaException(f"Expected one CXL memory node, but found {cxl_nodes}")
        return cxl_nodes[0]

    def get_numa_nodes(self) -> List[int]:
        _, numa_nodes = self._get_memory_nodes()
        if not numa_nodes:
            raise LisaException("No CPU-backed NUMA node is present")
        return numa_nodes

    def get_sysbench_memory_output(
        self,
        node_id: int,
        threads: int = 1,
        memory_scope: Optional[str] = None,
        memory_oper: Optional[str] = None,
        memory_block_size: Optional[str] = None,
        memory_access_mode: Optional[str] = None,
        memory_hugetlb: Optional[str] = None,
        memory_total_size: Optional[str] = None,
    ) -> ExecutableResult:
        command = f"--membind={node_id} sysbench --threads={threads} memory"
        options = {
            "memory-scope": memory_scope,
            "memory-oper": memory_oper,
            "memory-block-size": memory_block_size,
            "memory-access-mode": memory_access_mode,
            "memory-hugetlb": memory_hugetlb,
            "memory-total-size": memory_total_size,
        }
        for name, value in options.items():
            if value:
                command += f" --{name}={value}"
        command += " run"

        return self.run(
            command,
            timeout=1800,
            expected_exit_code=0,
            expected_exit_code_failure_message=(
                f"sysbench memory test failed on node {node_id}"
            ),
        )

    def get_node_speed(self, output: ExecutableResult) -> float:
        match = self._average_speed_pattern.search(output.stdout)
        if not match:
            raise LisaException("sysbench output does not contain memory throughput")
        return float(match.group(1))

    def get_node_time(self, output: ExecutableResult) -> float:
        match = self._total_time_pattern.search(output.stdout)
        if not match:
            raise LisaException("sysbench output does not contain total time")
        return float(match.group(1))

    def _get_memory_nodes(self) -> Tuple[List[int], List[int]]:
        result = self.run(
            "--hardware",
            expected_exit_code=0,
            expected_exit_code_failure_message="numactl failed to list NUMA nodes",
        )
        cxl_nodes: List[int] = []
        numa_nodes: List[int] = []
        for node_id, cpus in self._node_cpus_pattern.findall(result.stdout):
            target = numa_nodes if cpus.strip() else cxl_nodes
            target.append(int(node_id))
        return cxl_nodes, numa_nodes
