from __future__ import annotations

import http.client
import json
import socket
import time
from typing import Any
from urllib.parse import quote, urlencode


class DockerEngineError(RuntimeError):
    pass


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str) -> None:
        super().__init__("localhost", timeout=120)
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)


class DockerEngine:
    def __init__(self, socket_path: str = "/var/run/docker.sock") -> None:
        self.socket_path = socket_path

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        expected: set[int] | None = None,
    ) -> Any:
        connection = _UnixConnection(self.socket_path)
        encoded = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        try:
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            content = response.read()
        except OSError as exc:
            raise DockerEngineError(f"无法连接 Docker Engine: {exc}") from exc
        finally:
            connection.close()
        allowed = expected or {200, 201, 204, 304}
        if response.status not in allowed:
            detail = content.decode(errors="replace")[-500:]
            raise DockerEngineError(f"Docker API {method} {path} 返回 {response.status}: {detail}")
        if not content:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content.decode(errors="replace")

    def pull(self, repository: str, tag: str) -> None:
        query = urlencode({"fromImage": repository, "tag": tag})
        result = self._request("POST", f"/images/create?{query}", expected={200})
        if isinstance(result, str) and '"error"' in result:
            raise DockerEngineError(f"镜像拉取失败: {result[-500:]}")

    def find_compose_container(self, project: str, service: str) -> dict[str, Any]:
        filters = quote(
            json.dumps(
                {
                    "label": [
                        f"com.docker.compose.project={project}",
                        f"com.docker.compose.service={service}",
                    ]
                }
            )
        )
        rows = self._request("GET", f"/containers/json?all=1&filters={filters}", expected={200})
        if not rows:
            raise DockerEngineError("找不到需要更新的应用容器")
        return self.inspect(rows[0]["Id"])

    def inspect(self, container: str) -> dict[str, Any]:
        return self._request("GET", f"/containers/{quote(container, safe='')}/json", expected={200})

    def stop(self, container: str, timeout: int = 30) -> None:
        self._request(
            "POST", f"/containers/{quote(container, safe='')}/stop?t={timeout}", expected={204, 304}
        )

    def start(self, container: str) -> None:
        self._request("POST", f"/containers/{quote(container, safe='')}/start", expected={204, 304})

    def rename(self, container: str, name: str) -> None:
        self._request(
            "POST",
            f"/containers/{quote(container, safe='')}/rename?{urlencode({'name': name})}",
            expected={204},
        )

    def remove(self, container: str, force: bool = False) -> None:
        self._request(
            "DELETE",
            f"/containers/{quote(container, safe='')}?{urlencode({'force': str(force).lower()})}",
            expected={204},
        )

    def create_replacement(self, previous: dict[str, Any], image: str, name: str) -> str:
        config = previous["Config"]
        host = previous["HostConfig"]
        mounts = []
        for mount in previous.get("Mounts", []):
            source = mount.get("Name") if mount.get("Type") == "volume" else mount.get("Source")
            mounts.append(
                {
                    "Type": mount["Type"],
                    "Source": source,
                    "Target": mount["Destination"],
                    "ReadOnly": not mount.get("RW", True),
                }
            )
        endpoints: dict[str, Any] = {}
        for network_name, endpoint in previous["NetworkSettings"].get("Networks", {}).items():
            aliases = [
                alias
                for alias in (endpoint.get("Aliases") or [])
                if alias and alias != previous["Id"][:12]
            ]
            endpoints[network_name] = {"Aliases": aliases}
        host_config = {
            "Mounts": mounts,
            "PortBindings": host.get("PortBindings", {}),
            "RestartPolicy": host.get("RestartPolicy", {"Name": "unless-stopped"}),
        }
        for key in (
            "CapAdd",
            "CapDrop",
            "CpuShares",
            "LogConfig",
            "Memory",
            "NanoCpus",
            "PidsLimit",
            "ReadonlyRootfs",
            "SecurityOpt",
        ):
            if host.get(key) not in (None, 0, False, [], {}):
                host_config[key] = host[key]
        payload = {
            "Image": image,
            "Env": config.get("Env", []),
            "Labels": config.get("Labels", {}),
            "ExposedPorts": config.get("ExposedPorts", {"8000/tcp": {}}),
            "HostConfig": host_config,
            "NetworkingConfig": {"EndpointsConfig": endpoints},
        }
        result = self._request(
            "POST", f"/containers/create?{urlencode({'name': name})}", payload, expected={201}
        )
        return result["Id"]

    def wait_healthy(self, container: str, timeout: int = 120) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.inspect(container).get("State", {})
            health = state.get("Health", {}).get("Status")
            if health == "healthy" or (health is None and state.get("Running")):
                return
            if state.get("Status") in {"dead", "exited"} or health == "unhealthy":
                raise DockerEngineError(f"新容器启动失败: {health or state.get('Status')}")
            time.sleep(2)
        raise DockerEngineError("等待新容器健康检查超时")

    def replace_compose_service(
        self, project: str, service: str, repository: str, version: str
    ) -> None:
        previous = self.find_compose_container(project, service)
        previous_id = previous["Id"]
        name = previous["Name"].lstrip("/")
        rollback_name = f"{name}-rollback"
        image = f"{repository}:{version}"
        self.stop(previous_id)
        self.rename(previous_id, rollback_name)
        replacement_id: str | None = None
        try:
            replacement_id = self.create_replacement(previous, image, name)
            self.start(replacement_id)
            self.wait_healthy(replacement_id)
            self.remove(previous_id, force=True)
        except Exception:
            if replacement_id:
                try:
                    self.remove(replacement_id, force=True)
                except DockerEngineError:
                    pass
            self.rename(previous_id, name)
            self.start(previous_id)
            raise
