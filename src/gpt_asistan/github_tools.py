import subprocess, shlex, os
def run(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, check=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

def init_and_push(repo_path:str, repo_fullname:str, private:bool=False):
    vis = "--private" if private else "--public"
    run("git init -b main", cwd=repo_path)
    run("git add .", cwd=repo_path)
    run('git commit -m "init"', cwd=repo_path)
    # gh kullanıcı zaten girişliyse direkt oluşturup push eder
    run(f"gh repo create {shlex.quote(repo_fullname)} {vis} --source . --remote origin --push", cwd=repo_path)
    return True
