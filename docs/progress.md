# SDD ledger — plan: docs/superpowers/plans/2026-10-20-echokeys.md

执行方式：用户已批准当前会话直接实现。空目录无 Git 仓库，直接使用当前工作目录，不创建工作树、提交或分支合并。没有推送或发布。

Task 1: complete — 模型、正整数/有限非负间隔校验、鼠标路径/点击/双击/组合键、过滤拖拽/滚轮/ESC、忽略孤立释放、停止补释放；先运行缺少模块的失败测试，再实现，5/5 通过。

Task 2: complete — 3 秒可取消倒计时、任务互斥、单次测试固定一次、轮间等待、保留录制尾部时间、输入发送与异常释放、全局监听适配。单调时钟测试验证 10×3+2×2=34 秒。

Task 3: complete — 中文 Tk 界面、覆盖确认、按钮禁用、本地原子保存和启动恢复、不提供导入、退出保存提示、Windows 启动/打包脚本、README 和手工验收清单。

Final review: independent reviewer /root/review，只读检查代码并复现问题。发现 1 项 Important：极大有限间隔导致系统等待溢出。无 Critical 或延后的 Minor。

Final: fixed 极大间隔 — test_large_finite_interval_can_be_canceled_without_overflow RED→GREEN；等待按最多 60 秒分段，ESC 信号仍可立即唤醒。
Final: fixed 监听未就绪即可启动及关闭后重启监听 — 两项监听生命周期测试 RED→GREEN。
Final: fixed 监听启动错误消息交错、输入释放失败后仍可启动、关闭释放失败后仍可启动 — 三项回归测试 RED→GREEN。
Final: fixed 原窗口高度裁切 ESC 固定提示 — tools/gui_smoke.py 可见性断言先失败，按字体实际所需尺寸初始化后通过。

验证：32 项自动化测试通过；语法编译通过；使用自带 Python 3.12 / Tk 9 运行真实窗口的 GUI smoke，通过布局、按钮、模拟录制/测试、保存及关闭流程。GUI smoke 使用空输入后端，不安装全局监听，不控制真实鼠标键盘。截图保存于 docs/preview.png。

未验证：Windows 真实全局 ESC、鼠标键盘捕获/注入、混合 DPI 多屏表现、打包 EXE 及无 Python 机器运行。macOS 环境无法代替以上验收，没有生成或宣称已验证 Windows EXE。README 中有可执行的 Windows 验收清单。
