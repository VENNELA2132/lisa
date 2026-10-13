# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from typing import cast

from assertpy import assert_that

from lisa import (
    Logger,
    Node,
    TestCaseMetadata,
    TestSuite,
    TestSuiteMetadata,
    simple_requirement,
)
from lisa.operating_system import Posix, Ubuntu
from lisa.tools.mlc import Mlc
from lisa.tools.numactl import Numactl


@TestSuiteMetadata(
    area="cpu",
    category="performance",
    description="Verifies CXL memory performance against local NUMA memory.",
    requirement=simple_requirement(supported_os=[Ubuntu]),
)
class CXLPerformance(TestSuite):
    @TestCaseMetadata(
        description="""
        Verifies that the VM exposes one CPU-less CXL memory node, then checks
        that its latency is higher and its bandwidth is lower than local NUMA
        memory using sysbench and Intel MLC.
        """,
        priority=3,
        timeout=3600,
    )
    def verify_cxl_latency(self, node: Node, log: Logger) -> None:
        cast(Posix, node.os).install_packages(["sysbench"])

        numactl = node.tools[Numactl]
        cxl_node = numactl.get_cxl_node()
        numa_nodes = numactl.get_numa_nodes()
        log.info(f"Comparing CXL node {cxl_node} with NUMA nodes {numa_nodes}")

        cxl_output = numactl.get_sysbench_memory_output(
            node_id=cxl_node,
            memory_scope="local",
            memory_access_mode="rnd",
            memory_block_size="1M",
            memory_oper="write",
            memory_total_size="8G",
        )
        cxl_speed = numactl.get_node_speed(cxl_output)
        cxl_time = numactl.get_node_time(cxl_output)

        for numa_node in numa_nodes:
            numa_output = numactl.get_sysbench_memory_output(
                node_id=numa_node,
                memory_scope="local",
                memory_access_mode="rnd",
                memory_block_size="1M",
                memory_oper="write",
                memory_total_size="8G",
            )
            numa_speed = numactl.get_node_speed(numa_output)
            numa_time = numactl.get_node_time(numa_output)
            assert_that(cxl_speed).described_as(
                f"CXL node {cxl_node} speed should be lower than NUMA node "
                f"{numa_node}"
            ).is_less_than(numa_speed)
            assert_that(cxl_time).described_as(
                f"CXL node {cxl_node} time should be higher than NUMA node "
                f"{numa_node}"
            ).is_greater_than(numa_time)

        mlc = node.tools[Mlc]
        mlc_output = mlc.get_mlc_output()
        latency_data = mlc.get_latency_data(mlc_output)
        bandwidth_data = mlc.get_bandwidth_data(mlc_output)

        for numa_node in numa_nodes:
            assert_that(latency_data[numa_node][cxl_node]).described_as(
                f"CXL node {cxl_node} latency from NUMA node {numa_node} should "
                "be higher than local NUMA latency"
            ).is_greater_than(latency_data[numa_node][numa_node])
            assert_that(bandwidth_data[numa_node][cxl_node]).described_as(
                f"CXL node {cxl_node} bandwidth from NUMA node {numa_node} should "
                "be lower than local NUMA bandwidth"
            ).is_less_than(bandwidth_data[numa_node][numa_node])
