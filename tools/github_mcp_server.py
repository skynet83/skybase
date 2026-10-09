# -*- coding: utf-8 -*-
"""
GitHub MCP Server for SkyBase & AvitoHunter
Provides automated version snapshots, rollback, status, and history
directly to GitHub repository via GitHub REST API.
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from typing import Optional, List, Dict, Any

def get_configured_token() -> str:
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token.strip()
    try:
        cfg_p = os.path.expanduser("~/.gemini/config/mcp_config.json")
        if os.path.exists(cfg_p):
            with open(cfg_p, "r", encoding="utf-8") as fp:
                cfg = json.load(fp)
                t = cfg.get("mcpServers", {}).get("github-skybase", {}).get("env", {}).get("GITHUB_PERSONAL_ACCESS_TOKEN")
                if t:
                    return t.strip()
    except Exception:
        pass
    return ""

DEFAULT_TOKEN = get_configured_token()
DEFAULT_REPO = os.environ.get("GITHUB_REPO") or "skynet83/skybase"
WORKSPACE_DIR = os.environ.get("SKYBASE_WORKSPACE") or r"D:\ins\skybase"

# Каталоги и расширения для игнорирования
EXCLUDE_DIRS = {
    "__pycache__", ".git", "node_modules", "python-embed", "Lib", "lib",
    "test_build", "test_pyd", "build", "dist", "temp_chrome_profile",
    "bad_runtime_pkg", "profile", "img_cache", "1", "app", "browsers",
    "avito_browser_profile", "backups", "installer", "packages", "Default", "Profile 1"
}

EXCLUDE_EXTENSIONS = {
    ".pyc", ".pyo", ".log", ".pid", ".tmp", ".exe", ".pyd", ".dll", ".zip", ".7z", ".rom",
    ".whl", ".pak", ".dat", ".ldb", ".pma"
}


class GitHubClient:
    def __init__(self, token: str, repo: str):
        self.token = token.strip()
        self.repo = repo.strip()
        self.base_url = f"https://api.github.com/repos/{self.repo}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SkyBase-GitHub-MCP/1.0"
        }

    def _request(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Any:
        url = endpoint if endpoint.startswith("https://") else f"{self.base_url}/{endpoint.lstrip('/')}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = dict(self.headers)
        if data is not None:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_body = resp.read().decode("utf-8")
                return json.loads(resp_body) if resp_body else {}
        except urllib.error.HTTPError as he:
            err_msg = he.read().decode("utf-8", errors="ignore")
            try:
                err_json = json.loads(err_msg)
                msg = err_json.get("message", err_msg)
            except Exception:
                msg = err_msg
            raise RuntimeError(f"GitHub API HTTP {he.code} on {method} {url}: {msg}")
        except Exception as e:
            raise RuntimeError(f"GitHub API Error on {method} {url}: {e}")

    def get_latest_commit_sha(self, branch: str = "main") -> Optional[str]:
        try:
            ref_data = self._request(f"git/ref/heads/{branch}")
            return ref_data.get("object", {}).get("sha")
        except RuntimeError as e:
            if "404" in str(e) or "409" in str(e) or "empty" in str(e).lower():
                return None
            raise

    def get_tree_for_commit(self, commit_sha: str) -> Dict:
        commit_data = self._request(f"git/commits/{commit_sha}")
        tree_sha = commit_data["tree"]["sha"]
        return self._request(f"git/trees/{tree_sha}?recursive=1")

    def create_blob(self, content_bytes: bytes) -> str:
        b64 = base64.b64encode(content_bytes).decode("ascii")
        res = self._request("git/blobs", method="POST", data={"content": b64, "encoding": "base64"})
        return res["sha"]

    def create_tree(self, tree_items: List[Dict], base_tree: Optional[str] = None) -> str:
        payload = {"tree": tree_items}
        if base_tree:
            payload["base_tree"] = base_tree
        res = self._request("git/trees", method="POST", data=payload)
        return res["sha"]

    def create_commit(self, message: str, tree_sha: str, parents: List[str]) -> str:
        res = self._request("git/commits", method="POST", data={
            "message": message,
            "tree": tree_sha,
            "parents": parents
        })
        return res["sha"]

    def update_or_create_ref(self, branch: str, commit_sha: str):
        try:
            self._request(f"git/refs/heads/{branch}", method="PATCH", data={"sha": commit_sha, "force": True})
        except RuntimeError as e:
            if "404" in str(e) or "422" in str(e):
                self._request("git/refs", method="POST", data={"ref": f"refs/heads/{branch}", "sha": commit_sha})
            else:
                raise

    def list_commits(self, branch: str = "main", per_page: int = 15) -> List[Dict]:
        try:
            return self._request(f"commits?sha={branch}&per_page={per_page}")
        except RuntimeError as e:
            if "empty" in str(e).lower() or "409" in str(e) or "404" in str(e):
                return []
            raise

    def get_blob_content(self, sha: str) -> bytes:
        data = self._request(f"git/blobs/{sha}")
        enc = data.get("encoding")
        raw = data.get("content", "")
        if enc == "base64":
            return base64.b64decode(raw)
        return raw.encode("utf-8")


def should_include_file(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    for p in parts:
        if p in EXCLUDE_DIRS:
            return False
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in EXCLUDE_EXTENSIONS:
        return False
    fn = os.path.basename(rel_path).lower()
    if fn.startswith(".") or fn.endswith(".tmp"):
        return False
    return True


def collect_workspace_files(base_dir: str) -> Dict[str, str]:
    """Возвращает словарь {rel_path: abs_path} для всех исходных файлов."""
    res = {}
    for root, dirs, files in os.walk(base_dir):
        # Исключаем каталоги на лету для скорости
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in files:
            abs_p = os.path.join(root, f)
            rel_p = os.path.relpath(abs_p, base_dir).replace("\\", "/")
            if should_include_file(rel_p):
                try:
                    if os.path.getsize(abs_p) <= 5 * 1024 * 1024:
                        res[rel_p] = abs_p
                except Exception:
                    pass
    return res


# -----------------------------------------------------------------------------------
# Основная логика действий (сохранение, история, откат)
# -----------------------------------------------------------------------------------

def do_save_snapshot(message: str, branch: str = "main", workspace: str = WORKSPACE_DIR) -> Dict[str, Any]:
    client = GitHubClient(DEFAULT_TOKEN, DEFAULT_REPO)
    all_files = collect_workspace_files(workspace)

    parent_sha = client.get_latest_commit_sha(branch)

    # Загружаем блобы файлов
    tree_items = []
    for rel_p, abs_p in all_files.items():
        try:
            with open(abs_p, "rb") as fp:
                content_bytes = fp.read()
            blob_sha = client.create_blob(content_bytes)
            tree_items.append({
                "path": rel_p,
                "mode": "100644",
                "type": "blob",
                "sha": blob_sha
            })
        except Exception as e:
            print(f"[!] Warning reading {rel_p}: {e}", file=sys.stderr)

    tree_sha = client.create_tree(tree_items, base_tree=None)
    parents = [parent_sha] if parent_sha else []

    full_message = f"{message}\n\n[Snapshot: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"
    commit_sha = client.create_commit(full_message, tree_sha, parents)
    client.update_or_create_ref(branch, commit_sha)

    return {
        "status": "success",
        "commit_sha": commit_sha,
        "short_sha": commit_sha[:7],
        "message": message,
        "branch": branch,
        "files_count": len(tree_items),
        "url": f"https://github.com/{DEFAULT_REPO}/commit/{commit_sha}"
    }


def do_list_snapshots(limit: int = 15, branch: str = "main") -> List[Dict[str, Any]]:
    client = GitHubClient(DEFAULT_TOKEN, DEFAULT_REPO)
    raw_commits = client.list_commits(branch=branch, per_page=limit)
    res = []
    for c in raw_commits:
        res.append({
            "sha": c["sha"],
            "short_sha": c["sha"][:7],
            "message": c["commit"]["message"].splitlines()[0],
            "date": c["commit"]["author"]["date"],
            "author": c["commit"]["author"]["name"],
            "url": c["html_url"]
        })
    return res


def do_rollback_to_snapshot(commit_sha: str, workspace: str = WORKSPACE_DIR, dry_run: bool = False) -> Dict[str, Any]:
    client = GitHubClient(DEFAULT_TOKEN, DEFAULT_REPO)
    tree_data = client.get_tree_for_commit(commit_sha)

    restored_files = []
    for item in tree_data.get("tree", []):
        if item.get("type") == "blob":
            rel_p = item["path"]
            blob_sha = item["sha"]
            target_path = os.path.join(workspace, rel_p.replace("/", os.sep))

            if not dry_run:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                file_bytes = client.get_blob_content(blob_sha)
                with open(target_path, "wb") as fp:
                    fp.write(file_bytes)

            restored_files.append(rel_p)

    return {
        "status": "success",
        "dry_run": dry_run,
        "target_commit": commit_sha,
        "short_sha": commit_sha[:7],
        "restored_count": len(restored_files),
        "files": restored_files[:50]
    }


def do_get_status(workspace: str = WORKSPACE_DIR, branch: str = "main") -> Dict[str, Any]:
    client = GitHubClient(DEFAULT_TOKEN, DEFAULT_REPO)
    parent_sha = client.get_latest_commit_sha(branch)
    if not parent_sha:
        return {"status": "empty_remote", "message": "Репозиторий пока пуст."}

    tree_data = client.get_tree_for_commit(parent_sha)
    remote_files = {item["path"]: item["sha"] for item in tree_data.get("tree", []) if item.get("type") == "blob"}
    local_files = collect_workspace_files(workspace)

    modified = []
    added = []
    deleted = []

    for rel_p in local_files:
        if rel_p not in remote_files:
            added.append(rel_p)

    for rel_p in remote_files:
        if rel_p not in local_files:
            deleted.append(rel_p)

    return {
        "latest_commit": parent_sha[:7],
        "modified_or_added": len(added),
        "deleted_count": len(deleted),
        "added_sample": added[:10],
        "deleted_sample": deleted[:10]
    }


# -----------------------------------------------------------------------------------
# Model Context Protocol (MCP) Server Setup
# -----------------------------------------------------------------------------------

def create_mcp_app():
    from mcp.server.mcpserver import MCPServer
    app = MCPServer("github-skybase")

    @app.tool()
    def github_save_snapshot(message: str, branch: str = "main") -> str:
        """
        Создает контрольную точку (снимок/коммит) проекта и сохраняет все файлы в GitHub.
        Используйте для сохранения текущего рабочего состояния перед внесением изменений.
        """
        try:
            res = do_save_snapshot(message, branch)
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)

    @app.tool()
    def github_list_snapshots(limit: int = 15, branch: str = "main") -> str:
        """
        Возвращает список сохраненных контрольных точек (коммитов) с кратким описанием, датой и SHA.
        Используйте для поиска нужного момента времени для отката.
        """
        try:
            res = do_list_snapshots(limit, branch)
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)

    @app.tool()
    def github_rollback_to_snapshot(commit_sha: str, dry_run: bool = False) -> str:
        """
        Выполняет откат проекта к указанной контрольной точке (SHA коммита).
        Восстанавливает файлы локального проекта из удаленной копии GitHub.
        """
        try:
            res = do_rollback_to_snapshot(commit_sha, dry_run=dry_run)
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)

    @app.tool()
    def github_get_status() -> str:
        """
        Показывает текущий статус изменений в проекте относительно последней сохраненной точки в GitHub.
        """
        try:
            res = do_get_status()
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)

    return app


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in ("save", "commit"):
            msg = sys.argv[2] if len(sys.argv) > 2 else f"Автосохранение {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            print(f"[*] Создание снимка в GitHub ({DEFAULT_REPO})...")
            r = do_save_snapshot(msg)
            print(json.dumps(r, ensure_ascii=False, indent=2))
        elif cmd in ("list", "log"):
            print(f"[*] Список контрольных точек ({DEFAULT_REPO}):")
            r = do_list_snapshots()
            print(json.dumps(r, ensure_ascii=False, indent=2))
        elif cmd in ("rollback", "revert"):
            if len(sys.argv) < 3:
                print("Использование: python github_mcp_server.py rollback <commit_sha>")
                sys.exit(1)
            sha = sys.argv[2]
            print(f"[*] Откат к коммиту {sha}...")
            r = do_rollback_to_snapshot(sha)
            print(json.dumps(r, ensure_ascii=False, indent=2))
        elif cmd in ("status",):
            r = do_get_status()
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print(f"Неизвестная команда: {cmd}")
            sys.exit(1)
    else:
        # Режим MCP сервера (stdio)
        app = create_mcp_app()
        app.run(transport="stdio")
