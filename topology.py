class Topology:
    """
    Topology class to store info about the network.

    Servers is a dictionary indexed by server_id where the value is a tuple containing (IP, PORT)

    Neighbors is a dictionary indexed by server_id where the value is a list of tuples containing (neighbor_id, cost)
    """
    def __init__(self, servers, neighbors):
        self.servers = servers
        self.neighbors = neighbors

    def get_server_info(self, server_id):
        return self.servers.get(server_id)

    def get_neighbors_to_server(self, server_id):
        return self.neighbors.get(server_id)

    def remove_neighbor(self, server_id, neighbor_id):
        for index, (n_id, _) in enumerate(self.neighbors[server_id]):
            if n_id == neighbor_id:
                del self.neighbors[server_id][index]
                print(f'removed link to neighbor: {neighbor_id}')

    def update_cost(self, server_id, neighbor_id, new_cost):
        for index, item in enumerate(self.neighbors[server_id]):
            if item[0] == neighbor_id:
                self.neighbors[server_id][index] = (item[0], new_cost)
                break

    def __str__(self):
        return f'Servers: {[f"ID:{id} IP: {ip} PORT: {port}" for id, (ip, port) in self.servers.items()]}\n' +\
            f'Neighbors: {self.neighbors.items()}'


def topology_reader(file_path):
    """
    function to read a topology file to initialize a server
    """
    with open(file_path, 'r') as reader:
        num_servers = int(reader.readline())
        num_neighbors = int(reader.readline())
        servers = {}
        neighbors = {}
        for _ in range(num_servers):
            server_line_split = reader.readline().replace('\n', '').split(' ')
            servers[int(server_line_split[0])] = (server_line_split[1], int(server_line_split[2]))
        for _ in range(num_neighbors):
            neighbor_line_split = reader.readline().replace('\n', '').split(' ')
            if neighbors.get(int(neighbor_line_split[0])):
                neighbors[int(neighbor_line_split[0])].append((int(neighbor_line_split[1]), int(neighbor_line_split[2])))
            else:
                neighbors[int(neighbor_line_split[0])] = [(int(neighbor_line_split[1]), int(neighbor_line_split[2]))]
        return Topology(servers, neighbors)


