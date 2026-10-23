"""repo-dissect 回归测试：专门构造"明知有问题"的文档，确认脚本能报出来，而不是给出虚假的"通过"。

用法（只用标准库，Python 3.8+，需要 git）:
  python3 tests/run_tests.py
所有用例都在临时目录里运行，不联网，不改动仓库里的文件。发版前跑一遍，全部通过才发布。
用例来源：用户和 Agent 的运行复盘（续行归属、六块检查、改名绕过、链接文字与锚点不一致等）。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
PY = sys.executable
results = []


def run(args, cwd, env=None):
    r = subprocess.run([PY, "-B"] + args, cwd=cwd, capture_output=True, env=env)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")


def case(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"\n     {detail[:600]}"))


def git(repo, *a):
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.com"] + list(a),
                   check=True, capture_output=True)


def make_repo(base):
    """一个小 git 仓库：两个 10 行的源文件、测试代码、测试素材、一个 CI 配置"""
    src = os.path.join(base, "src")
    files = {
        "a/one.ts": "".join(f"export const a{i} = {i};\n" for i in range(1, 11)),
        "b/two.ts": "".join(f"export const b{i} = {i};\n" for i in range(1, 11)),
        "tests/test_x.py": "def test_x():\n    assert True\n",
        "tests/fixtures/sample.py": "DATA = 1\n",
        "tests/fixtures/data.json": "{}\n",
        "package.json": '{"name": "x", "dependencies": {"openai": "^4.0.0", "react": "^18"}}\n',
        "skills/demo/SKILL.md": "---\nname: demo\ndescription: demo skill\n---\n# Demo\n",
        "src/hooks/useThing.ts": "export const useThing = () => 1;\n",
        ".github/workflows/ci.yml": ("name: ci\non: push\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n"
                                     "      - uses: actions/checkout@v4\n      - run: pip install pytest pytest-cov\n"
                                     "      - run: which pytest || echo none\n      - run: pytest -q\n"
                                     "      - run: mvn install -Dmaven.test.skip=true\n"),
    }
    for p, t in files.items():
        os.makedirs(os.path.dirname(os.path.join(src, p)), exist_ok=True)
        with open(os.path.join(src, p), "w", encoding="utf-8") as f:
            f.write(t)
    git(src, "init", "-q")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "init")
    sha = subprocess.run(["git", "-C", src, "rev-parse", "HEAD"], capture_output=True).stdout.decode().strip()
    return src, sha


def write(d, name, text):
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        f.write(text)
    return os.path.join(d, name)


def checklinks(src, sha, out, *files, fix=False):
    args = [os.path.join(SCRIPTS, "checklinks.py"), src, "o/r", sha] + (["--fix"] if fix else []) + list(files)
    return run(args, out)


def main():
    base = tempfile.mkdtemp(prefix="rd-tests-")
    try:
        src, sha = make_repo(base)
        out = os.path.join(base, "out")
        os.makedirs(out)
        P = f"https://github.com/o/r/blob/{sha}"

        # 1. 续行换了段落：不能沿用上一段（表格里）别的文件
        f1 = write(out, "02-续行.md", "## 1. 小节\n\n本段讲 `a/one.ts:1`。\n\n| 项 | 证据 |\n|---|---|\n"
                                      "| 另一件事 | `b/two.ts:2` |\n\n回到刚才那个文件，继续写 `:3-4`。\n")
        rc, o = checklinks(src, sha, out, f1)
        case("续行换段落后不沿用别的文件", rc == 1 and "找不到所属文件" in o and "文件 b/two.ts" not in o.split("`:3-4`")[-1][:40], o)

        # 2. 同一段里两个文件后接续行：报歧义
        f2 = write(out, "02-歧义.md", f"## x\n\n先 [a/one.ts:L1]({P}/a/one.ts#L1) 再 [b/two.ts:L2]({P}/b/two.ts#L2)，接着 `:5`。\n")
        rc, o = checklinks(src, sha, out, f2)
        case("同段两个文件后的续行报歧义", rc == 1 and "归属有歧义" in o, o)

        # 3. 表格行、列表项内的续行正常归属
        f3 = write(out, "02-正常.md", f"## x\n\n| 项 | 证据 |\n|---|---|\n| A | [a/one.ts:L1]({P}/a/one.ts#L1)、`:3` |\n"
                                      f"| B | [b/two.ts:L2]({P}/b/two.ts#L2)、`:4` |\n\n- 列表 [b/two.ts:L5]({P}/b/two.ts#L5) 接 `:6`\n")
        rc, o = checklinks(src, sha, out, f3)
        case("表格行和列表项里的续行按本行归属", "（续行，文件 a/one.ts）" in o and o.count("（续行，文件 b/two.ts）") == 2
             and "歧义" not in o and "找不到所属文件" not in o, o)

        # 4. --fix 列出改写明细，续行单独列出，并自动再核验一遍
        f4 = write(out, "02-fix.md", "## x\n\n见 `a/one.ts:1` 和续行 `:3`。\n")
        rc, o = checklinks(src, sha, out, f4, fix=True)
        fixed = open(f4, encoding="utf-8").read()
        case("--fix 列出明细并自动复核", "续行展开" in o and "只读核验" in o and "a/one.ts#L3" in fixed and rc == 0, o)

        # 5. 链接文字和锚点不一致
        f5 = write(out, "02-锚点.md", f"## x\n\n[a/one.ts:L2-L4-L1]({P}/a/one.ts#L1-L4) 和 [b/two.ts:L3]({P}/a/one.ts#L3)\n")
        rc, o = checklinks(src, sha, out, f5)
        case("链接文字与锚点不一致要报错", rc == 1 and "链接文字写的是" in o and "链接文字的文件" in o, o)

        # 6. L4 只有"没精读的关键机制"标题：核心机制一块不能算满足
        l4 = (f"## 0. 没精读的关键机制\n\n见 [a/one.ts:L1]({P}/a/one.ts#L1)\n\n## 1. 阅读路线\n\n## 2. 适用条件与可借鉴之处\n\n## 3. 技术债\n")
        f6 = write(out, "04-核心模块-x.md", l4)
        rc, o = checklinks(src, sha, out, f6)
        case("L4 六块不被'没精读的机制'标题骗过", rc == 1 and "核心机制（算法或不变量）" in o, o)

        # 7. L4 改名后仍然检查，并提示改名
        f7 = write(out, "04_核心模块-y.md", l4)
        rc, o = checklinks(src, sha, out, f7)
        case("L4 改名后检查不失效", rc == 1 and "缺少规定内容" in o and "请用 04-核心模块" in o, o)

        # 8. 选题依据像是自己定的：给提示
        write(out, "index.md", "# idx\n\n选题依据：我判断生成期机制最有价值，选了 #1 #2\n\n## 关键结论核对表\n")
        rc, o = checklinks(src, sha, out, f6)
        case("选题依据自己定的会提示", "像是自己定的" in o, o)
        os.remove(os.path.join(out, "index.md"))

        # 9. 全称句清单分强弱；只核验一部分文档时保留其他文档的条目；全部核验且没有全称句时删掉旧清单
        f9 = write(out, "03-流程.md", f"## x\n\n失败一律返回空 [a/one.ts:L1]({P}/a/one.ts#L1)。\n\n只有管理员能改 [a/one.ts:L2]({P}/a/one.ts#L2)。\n")
        checklinks(src, sha, out, f9)
        lst = open(os.path.join(out, "_全称句清单.txt"), encoding="utf-8").read()
        case("全称句清单分强弱档", "强 1 句" in lst and "弱 1 句" in lst, lst)
        f9s = write(out, "05-其他.md", f"## x\n\n普通描述 [a/one.ts:L1]({P}/a/one.ts#L1)。\n")
        checklinks(src, sha, out, f9s)
        lst2 = open(os.path.join(out, "_全称句清单.txt"), encoding="utf-8").read() if os.path.exists(os.path.join(out, "_全称句清单.txt")) else ""
        case("只核验部分文档时保留其他文档的清单条目", "03-流程.md" in lst2, lst2)
        os.remove(f9s)
        write(out, "03-流程.md", f"## x\n\n普通描述 [a/one.ts:L1]({P}/a/one.ts#L1)。\n")
        others = [os.path.join(out, n) for n in os.listdir(out) if n.endswith(".md") and (n[0].isdigit() or n == "compare.md")]
        rc, o = checklinks(src, sha, out, *others)
        case("没有全称句时删掉旧清单", not os.path.exists(os.path.join(out, "_全称句清单.txt")), o)

        # 9b. 别的仓库的链接（对比模式、依赖库）后面的续行，不能借用本仓库的路径
        Q = "https://github.com/other/repo/blob/" + "0" * 40
        f9b = write(out, "compare.md", f"| 入口 | [a/one.ts:L1]({P}/a/one.ts#L1) | [x/main.py:L2]({Q}/x/main.py#L2)、`:5` |\n")
        rc, o = checklinks(src, sha, out, f9b)
        case("别的仓库链接后的续行不借用本仓库路径", rc == 1 and "歧义" in o and "文件 a/one.ts" not in o, o)

        # 9c. 出错的引用后面的续行，不能越过它借用更前面的路径
        f9c = write(out, "02-坏引用.md", "## x\n\n`a/one.ts:1` 和 `missing.ts:2`、`:7`\n")
        rc, o = checklinks(src, sha, out, f9c)
        case("坏引用后的续行不借用更前面的路径", "文件 a/one.ts）" not in o.split("`:7`")[-1][:30] and "`:7`" in o and "歧义" in o, o)

        # 9d. 代码块之后的行号、CRLF 换行保持不变
        f9d = os.path.join(out, "02-行号.md")
        with open(f9d, "w", encoding="utf-8", newline="") as fh:
            fh.write("## x\r\n\r\n```\r\nl1\r\nl2\r\nl3\r\n```\r\n\r\n见 `a/one.ts:2`\r\n")
        rc, o = checklinks(src, sha, out, f9d, fix=True)
        raw = open(f9d, "rb").read()
        case("--fix 明细行号正确", "第 9 行" in o, o)
        case("--fix 保留 CRLF 换行", raw.count(b"\r\n") == 9 and b"a/one.ts#L2" in raw, repr(raw[:200]))

        # 9e. 链接文字带说明前缀不算不一致
        f9e = write(out, "02-前缀.md", f"## x\n\n[主入口 a/one.ts:L5]({P}/a/one.ts#L5)\n")
        rc, o = checklinks(src, sha, out, f9e)
        case("链接文字带说明前缀不误报", rc == 0, o)

        # 9f. 引用块里的空 > 行也是段落边界
        f9f = write(out, "02-引用块.md", "## x\n\n> 见 `a/one.ts:1`\n>\n> 接着 `:3`\n")
        rc, o = checklinks(src, sha, out, f9f)
        case("引用块里的空行也分段", "找不到所属文件" in o, o)

        # 10. repo_stats：测试素材、CI 步骤识别
        rc, o = run([os.path.join(SCRIPTS, "repo_stats.py"), src, "--json", os.path.join(base, "s.json")], base)
        st = json.load(open(os.path.join(base, "s.json"), encoding="utf-8"))
        steps = [x["text"] for x in st["ci"]["test_steps"]]
        case("repo_stats 把 fixtures 下的 .py 算测试素材", st["tests"]["code_files"] == 1 and st["tests"]["fixture_files"] == 2, o)
        case("repo_stats 不把安装、跳过测试的命令算成跑测试", steps == ["- run: pytest -q"], json.dumps(steps, ensure_ascii=False))
        case("repo_stats 给出规模判定", st.get("size", {}).get("large") is False and "规模判定" in o, o)

        case("repo_stats 找到大模型依赖和技能文件", "openai" in st["ai"]["sdk"] and st["ai"]["assets"].get("技能（SKILL.md）") == 1
             and "hook" not in st["ai"]["assets"], json.dumps(st["ai"], ensure_ascii=False))

        # 10b. AI 项目：画像没写 AI 形态要提示；写了 Agent 型、技术架构没有 Harness 清单要提示；长代码块要提示
        ai_dir = os.path.join(base, "ai")
        os.makedirs(ai_dir)
        g0 = write(ai_dir, "00-画像.md", f"## x\n\n这是一个调用大模型的项目 [a/one.ts:L1]({P}/a/one.ts#L1)\n")
        rc, o = checklinks(src, sha, ai_dir, g0)
        case("AI 项目画像没写 AI 形态会提示", "没写「AI 形态」" in o, o)
        write(ai_dir, "00-画像.md", f"## x\n\nAI 形态：Agent 型 [a/one.ts:L1]({P}/a/one.ts#L1)\n")
        code = "\n".join(f"line{i}" for i in range(20))
        g2 = write(ai_dir, "02-技术架构.md", f"## x\n\n见 [a/one.ts:L2]({P}/a/one.ts#L2)\n\n```python\n{code}\n```\n\n```mermaid\nflowchart LR\n{code}\n```\n")
        rc, o = checklinks(src, sha, ai_dir, g0, g2)
        case("Agent 型缺 Harness 清单会提示", "Harness 清单" in o, o)
        case("超过 15 行的代码块会提示（mermaid 不算）", "1 段代码超过 15 行（20 行）" in o, o)

        # 10c. AI 线索的误报和漏报：只读依赖段；第三方目录、文档目录、根目录的开发用 Agent 配置不算资产
        fx = os.path.join(base, "aifx")
        for rel, body in {
            "pyproject.toml": '[project]\nname = "x"\nkeywords = ["ai", "openai"]\ndependencies = [\n  "langchain_openai>=0.1",\n]\n',
            "requirements.txt": "# transformers is not used\nllama_index.core==0.10\n",
            "go.mod": "module x\n\nrequire (\n\tgithub.com/openai/openai-go/v2 v2.0.0\n)\n",
            "node_modules/y/SKILL.md": "---\ndescription: vendored\n---\n",
            "docs/agents/zabbix.md": "# Zabbix agent\n", "docs/commands/install.md": "# install\n",
            "src/hooks/config.json": "{}\n", ".claude/agents/dev.md": "# dev helper\n",
        }.items():
            os.makedirs(os.path.dirname(os.path.join(fx, rel)) or fx, exist_ok=True)
            write(fx, rel, body)
        rc, o = run([os.path.join(SCRIPTS, "repo_stats.py"), fx, "--json", os.path.join(base, "fx.json")], base)
        fa = json.load(open(os.path.join(base, "fx.json"), encoding="utf-8"))["ai"]
        case("AI 线索只读依赖段，名字按规范化比对", sorted(fa["sdk"]) == ["github.com/openai/openai-go", "langchain_openai", "llama_index.core"],
             json.dumps(fa["sdk"], ensure_ascii=False))
        case("第三方目录、文档目录、开发用 Agent 配置不算 Agent 资产", fa["assets"] == {} and fa["dev_agent_config_files"] == 1,
             json.dumps(fa, ensure_ascii=False))

        # 10d. 四个反引号的代码块成对识别；AI 形态的提示只看这一行、混合型只要求主形态的专项
        fence_dir = os.path.join(base, "fence")
        os.makedirs(fence_dir)
        g3 = write(fence_dir, "03-主流程.md", f"## x\n\n见 [a/one.ts:L2]({P}/a/one.ts#L2)\n\n````md\n```bash\n{code}\n```\n````\n\n"
                   "````\nshort\n````\n\n" + "\n".join(f"正文 {i}" for i in range(20)) + "\n\n```bash\nls\n```\n")
        rc, o = checklinks(src, sha, fence_dir, g3)
        case("四个反引号的代码块成对识别", "1 段代码超过 15 行（22 行）" in o, o)
        for sub, t00, t02, want, unwanted in (
            ("ua", "## x\n\n请求头带 User-Agent，部署 SSH Agent", "", None, "AI 形态"),
            ("mix", "## x\n\nAI 形态：混合型，嵌入型为主，次形态是 Agent 型", "## AI 链路表\n", None, "Harness"),
            ("mix2", "## x\n\nAI 形态：混合型", "## y\n", "没写哪种为主", None),
            ("none", "## x\n\nAI 形态：非 AI（既不是嵌入型也不是 Agent 型）\n\n判断 Agent 型要看循环", "## y\n", None, "提示：画像"),
        ):
            dd = os.path.join(base, "form-" + sub)
            os.makedirs(dd)
            fs = [write(dd, "00-画像.md", t00 + f"\n\n见 [a/one.ts:L1]({P}/a/one.ts#L1)\n")]
            if t02:
                fs.append(write(dd, "02-技术架构.md", t02))
            rc, o = checklinks(src, sha, dd, *fs)
            case(f"AI 形态提示：{sub}", (want is None or want in o) and (unwanted is None or unwanted not in o), o)

        # 11. build_report：inline 方式要提示没做渲染校验、字节数带单位
        ex = os.path.join(ROOT, "examples", "ragflow")
        if os.path.isdir(ex):
            rep = os.path.join(base, "rep")
            shutil.copytree(ex, rep)
            rc, o = run([os.path.join(SCRIPTS, "build_report.py"), rep, "--mermaid", "inline"], base)
            case("build_report inline 提示未做渲染校验", rc == 0 and "没有在生成时渲染过" in o and "字节" in o and "校验码" in o, o)

            # 12. 首屏格式：机制卡用候选表原名；学习目标不写选型建议；提示条里的 ✅ 也转成标签
            with open(os.path.join(rep, "report.json"), encoding="utf-8") as fh:
                cfg = json.load(fh)
            cfg["goal"] = "架构学习"
            cfg["verdict"]["summary"] = "值得学习，建议内部小范围试点"
            cfg["stats"][0] = ["10s → 7s", "机制 · 不存在的机制", "说明"]
            cfg["stats"][1] = ["规则", "机制 · hook 超时预算", "说明"]
            cfg["notice"] = {"text": "✅ 结论都有出处", "tone": "warn"}
            with open(os.path.join(rep, "report.json"), "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, ensure_ascii=False)
            write(rep, "02-机制.md", "# x\n\n## 机制候选\n\n| 机制 | 说明 |\n|---|---|\n| hook 超时预算 | a |\n")
            rc, o = run([os.path.join(SCRIPTS, "build_report.py"), rep, "--mermaid", "inline"], base)
            html_ = open(os.path.join(rep, "report.html"), encoding="utf-8").read()
            alert = html_[html_.find('<div class="alert warn">'):][:600]
            case("机制卡名字不在候选表里会提示", "不存在的机制" in o and "hook 超时预算」在 L2" not in o, o)
            case("学习目标的首屏写选型建议会提示", "首屏却有选型建议「试点」" in o, o)
            case("提示条里的 ✅ 转成标签", "✅" not in alert and "事实" in alert, alert)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    print(f"\n共 {len(results)} 项，通过 {len(results) - len(failed)} 项" + (f"，失败 {len(failed)} 项" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
