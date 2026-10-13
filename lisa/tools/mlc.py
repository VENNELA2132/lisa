# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import re
from pathlib import PurePath
from typing import Dict, List

from lisa.executable import Tool
from lisa.tools.curl import Curl
from lisa.tools.echo import Echo
from lisa.tools.ln import Ln
from lisa.tools.tar import Tar
from lisa.util import LisaException
from lisa.util.process import ExecutableResult


class Mlc(Tool):
    _mlc_package_url = "https://downloadmirror.intel.com/926327/mlc_v3.13.tgz"
    _mlc_package_name = "mlc_v3.13.tgz"
    _table_header_pattern = re.compile(r"^\s*Numa node\s+((?:\d+\s*)+)$")
    _table_row_pattern = re.compile(
        r"^\s*(?P<node>\d+)\s+(?P<values>(?:\d+(?:\.\d+)?\s*)+)$"
    )

    @property
    def command(self) -> str:
        return "mlc"

    @property
    def can_install(self) -> bool:
        return True

    def _install(self) -> bool:
        package_path = self.node.working_path.joinpath(self._mlc_package_name)
        extract_path = self.node.working_path.joinpath("mlc")
        self.node.tools[Curl].fetch(
            url=self._mlc_package_url,
            arg=f"-L -o {package_path}",
            execute_arg="",
        )
        self.node.tools[Tar].extract(
            file=str(package_path),
            dest_dir=str(extract_path),
        )
        self.node.tools[Ln].create_link(
            target=str(extract_path.joinpath("Linux", "mlc")),
            link="/usr/local/bin/mlc",
            force=True,
        )
        return self._check_exists()

    def get_mlc_output(self) -> ExecutableResult:
        self.node.tools[Echo].write_to_file(
            "4000", PurePath("/proc/sys/vm/nr_hugepages"), sudo=True
        )
        return self.run(
            sudo=True,
            timeout=1800,
            expected_exit_code=0,
            expected_exit_code_failure_message=(
                "MLC failed to measure memory performance"
            ),
        )

    def get_latency_data(self, output: ExecutableResult) -> Dict[int, Dict[int, float]]:
        return self._parse_table(
            output.stdout,
            "Measuring idle latencies for random access",
        )

    def get_bandwidth_data(
        self, output: ExecutableResult
    ) -> Dict[int, Dict[int, float]]:
        return self._parse_table(
            output.stdout,
            "Measuring Memory Bandwidths between nodes within system",
        )

    def get_node_details(
        self, node_id: int, data: Dict[int, Dict[int, float]]
    ) -> List[float]:
        missing_sources = [
            source_node for source_node, values in data.items() if node_id not in values
        ]
        if missing_sources:
            raise LisaException(
                f"MLC output has no values for node {node_id} from source nodes "
                f"{missing_sources}"
            )
        return [values[node_id] for values in data.values()]

    def _parse_table(
        self, output: str, section_marker: str
    ) -> Dict[int, Dict[int, float]]:
        section_start = output.find(section_marker)
        if section_start < 0:
            raise LisaException(f"MLC output does not contain '{section_marker}'")

        node_ids: List[int] = []
        rows: Dict[int, Dict[int, float]] = {}
        for line in output[section_start:].splitlines():
            if not node_ids:
                header_match = self._table_header_pattern.match(line)
                if header_match:
                    node_ids = [
                        int(node_id) for node_id in header_match.group(1).split()
                    ]
                continue

            row_match = self._table_row_pattern.match(line)
            if row_match:
                values = [float(value) for value in row_match.group("values").split()]
                if len(values) != len(node_ids):
                    raise LisaException(
                        "MLC table column count does not match its NUMA node header"
                    )
                rows[int(row_match.group("node"))] = dict(zip(node_ids, values))
            elif rows and line.strip():
                break

        if not rows:
            raise LisaException(f"MLC output has no data for '{section_marker}'")
        return rows
