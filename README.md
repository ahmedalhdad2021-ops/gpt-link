# GPT直链提链

Gpt的 Session / accessToken 提链工具。

## 下载

打开仓库页面后点 `Code` -> `Download ZIP`，解压后进入文件夹。

仓库地址：

```text
https://github.com/mika50000/gpt-link
```

## Windows 启动

双击 `start.bat`，或运行：

```bat
cd /d "%USERPROFILE%\Downloads\gpt-link-main"
start.bat
```

## macOS 启动

需要先有 Python 3；如果终端提示找不到 `python3`，先安装 Python 3。

第一次运行如果不能双击，先打开终端执行：

```bash
cd ~/Downloads/gpt-link-main
chmod +x start.command start.sh
./start.command
```

之后可以直接双击 `start.command`。

## Linux 启动

```bash
cd ~/Downloads/gpt-link-main
chmod +x start.sh
./start.sh
```

## 手动启动

所有系统都可以用 Python 手动启动：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Windows PowerShell 手动启动：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

默认地址：

```text
http://127.0.0.1:8801
```

## 功能

- 直接导入 ChatGPT Session JSON / accessToken
- 创建代理池 / 优惠代理池
- PLUS · PH_SHORT · 目标 0
- 短链、外链、Stripe Hosted、金额校验、批量结果

Session / Token 不会写入本地文件；只会保存代理池和尝试次数设置。本地保存目录 `data/` 已被 `.gitignore` 排除，不会上传到 GitHub。
