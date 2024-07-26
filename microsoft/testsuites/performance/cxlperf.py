

from pathlib import PurePath
from lisa.base_tools.uname import Uname
from lisa.base_tools.wget import Wget
from lisa.environment import Environment
from lisa import (
    LisaException,
    Logger,
    Node,
    SkippedException,
    TestCaseMetadata,
    TestSuite,
    TestSuiteMetadata,
    simple_requirement,
)
from lisa.operating_system import Ubuntu
from lisa.tools.mkdir import Mkdir
from lisa.tools.tar import Tar
from lisa.util import UnsupportedDistroException
from lisa.util.logger import Logger


@TestSuiteMetadata(
    area="cpu",
    category="performance",
    description="""
    This test suite verifies the latency of cxl node when compared to numa node
    """,
)

class CXLPerformance(TestSuite):
    
    @TestCaseMetadata(
        description="""
        This test case check the following for a VM with only 1 CXL node.
        1) Checks if CXL node is present in the VM.
        2) Verifies that CXL node time and latency is greater than that of NUMA node.
        3) Verifies that CXL node bandwidth and speed are less than that of NUMA node. 
        """,
    )
    def verify_cxl_latency(
        self, environment: Environment, node: Node, log: Logger
    ) -> None:
        self._install_dependencies(node)
        mlc_pkg = "https://downloadmirror.intel.com/822971/mlc_v3.11a.tgz"

        #Run numactl -H
        #check for available nodes
        #confirm that the last node does not contain any cpus

        result = node.execute("numactl -H")
        print("VENNELA",result)
        cxl_node,numa_nodes = self.get_cxl_node_and_numa_nodes(str(result))
        print("VENNELA",cxl_node,numa_nodes)
        #Run sysbench which required parameters for cxl and numa
        #check for execution time and speed of execution to transfer 8gb
        #Sysbench output as follows -->
        #sysbench 1.0.20 
        #
        #Running the test with following options:
        #......
        #8192.00MiB transferred (183.53 MiB/sec)
        #......
        #General statistis:
        #   total time:     44.6566s
        #......
        sysbench_cxl_output = node.execute(f"numactl --membind {cxl_node} sysbench --threads=1 memory --memory-scope=local --memory-oper=write --memory-block-size=8g --memory-access-mode=rnd run")
        print(sysbench_cxl_output)
        cxl_speed , cxl_time = self.sysbench_output_extract(str(sysbench_cxl_output))
        print(cxl_speed,cxl_time)
        
        for i in range(numa_nodes):
            sysbench_numa_output = node.execute(f"numactl --membind {i} sysbench --threads=1 memory --memory-scope=local --memory-oper=write --memory-block-size=8g --memory-access-mode=rnd run")
            print(sysbench_numa_output)
            numa_speed , numa_time = self.sysbench_output_extract(str(sysbench_numa_output))
            print(numa_speed,numa_time)
            #Confirm that speed of cxl node is less than numa node and time taken for CXL node is more than that of numa node
            if not (cxl_speed<numa_speed and cxl_time>numa_time):
                raise LisaException()
        
        print("VENNELA sysbench executed succesfully")
        #wget memory latency checker (mlc) 
        #add 4000 to /proc/sys/vm/nr_hugepages and run mlc
        #compare the latency and bandwidth from the output
        #mlc output -->
        #Intel(R) Memory Latency Checker - v3.11
        #...
        #...
        #Measuring idle latencies for random access (in ns)...
        #           Numa node
        # Numa node           0       1       2
        #      0         130.2  231.2   265.7
        #      1         238.2  130.1   368.7
        #...
        #Measuring Memory Bandwidths between nodes within system
        #Using Read-only traffic type
        #       Numa node
        # Numa node           0       1       2
        #      0        79808.6 60065.8 31322.0
        #      1        68081.3 78793.6 27324.0
        #...
        
        cmd_path = self.download(mlc_pkg,node)
        echo_cmd="echo 4000 > /proc/sys/vm/nr_hugepages"
        node.execute(echo_cmd,sudo=True,sudo=True,shell=True)
        mlc_output = node.execute("./mlc",sudo=True,cwd=cmd_path)
        print("VENNELA mlc o/p",mlc_output)
        print("-----------------------------------")
        cxl_latencies,cxl_bandwidths,numa_latencies,numa_bandwidths = self.mlc_output_extract(str(mlc_output),numa_nodes)
        print(cxl_latencies,cxl_bandwidths,numa_latencies,numa_bandwidths)
        if not (all(all(cxl_latencies[i] > b for b in numa_latencies[i]) for i in range(len(numa_latencies)))):
            raise LisaException()   
        
        if not (all(all(cxl_bandwidths[i] < b for b in numa_bandwidths[i]) for i in range(len(numa_bandwidths)))):
            raise LisaException()
        
        return
    
    def _install_dependencies(self, node: Node) -> None:
        ubuntu_required_packages = [
            "numactl",
            "sysbench",
            "hwloc",
            "wget"
        ]
        if isinstance(node.os, Ubuntu) and node.os.information.version >= "2.4.0":
            node.os.install_packages(ubuntu_required_packages)
        else:
            raise UnsupportedDistroException(
                node.os,
                "Only CentOS 7.6-8.3, Ubuntu 18.04-22.04 distros are "
                "supported by the HPC team. Also supports CBLMariner 2.0 "
                "distro which uses the Mellanox inbox driver",
            )
        
    def get_cxl_node_and_numa_nodes(self, output: str) -> str:
        lines = output.strip().splitlines()
        for line in lines:
            if "available:" in line:
                total_nodes = int(line.split()[1])
            if "cpus:" in line:
                node, cpus = line.split(' cpus:')
                if not cpus.strip():
                    cxl_node_number=node.split(' ')[1]

        return cxl_node_number,total_nodes-1
    
    def sysbench_output_extract(self, output: str):
        lines = output.strip().splitlines()
        speed=0
        time=0
        for line in lines:
            if "MiB transferred" in line:
                speed = float(line.split('(')[1].split(' ')[0])
            if "total time" in line:
                time = float(line.split(':')[1].split('s')[0].strip())
        return speed, time
    
    def mlc_output_extract(self, output: str,numa_nodes):
        lines = output.strip().splitlines()

        # Extract latency data
        latency_data = []
        found=False
        for i,line in enumerate(lines):
          if "Measuring idle latencies" in line:
            found = True

          if (found and line.startswith("Numa node")):
              for j in range(numa_nodes):
                # print(lines[i+j+1])
                latency_data.append([float(x) for x in lines[i+j+1].split()])
              break

        # Convert latency values to float
        cxl_latencies= [data[numa_nodes+1] for data in latency_data]
        numa_latencies = [data[1:numa_nodes+1] for data in latency_data]

        # Extract bandwidth data
        bandwidth_data=[]
        found=False
        for i,line in enumerate(lines):
          if "Measuring Memory Bandwidths" in line:
            found = True

          if (found and line.startswith("Numa node")):
              for j in range(numa_nodes):
                # print(lines[i+j+1])
                bandwidth_data.append([float(x) for x in lines[i+j+1].split()])
              break

        # Convert latency values to float
        cxl_bandwidth= [data[numa_nodes+1] for data in bandwidth_data]
        numa_bandwidths = [data[1:numa_nodes+1] for data in bandwidth_data]

        return cxl_latencies,cxl_bandwidth,numa_latencies,numa_bandwidths
    
    
    
    def download(self,package,node:Node) -> PurePath:
        if not node.shell.exists(node.working_path.joinpath("mlc")):
            wget_tool = node.tools[Wget]
            # mkdir_tool = node.tools[Mkdir]
            tar = node.tools[Tar]
            
            pkg_path = wget_tool.get(package, str(node.working_path))
            # mkdir_tool.create_directory(str(node.working_path)+"mlc")
            tar.extract(file=pkg_path, dest_dir=str(node.working_path.joinpath("mlc")))

            return node.working_path.joinpath("mlc/Linux")
        
        