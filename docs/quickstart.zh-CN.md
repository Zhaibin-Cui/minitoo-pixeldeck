# MiniToo Pixeldeck 中文快速上手

这是独立的 MiniToo 像素开发工具。电脑运行程序，通过蓝牙发送画面；没有替换设备固件。代码、主文档和像素界面以英文为主。

## 架构

协议编解码 → 蓝牙驱动 → 最新帧发送器 → 可扩展 demo。输入通过回调和管道推送，与传图分开。静止页面不重复上传，暂停动画会取消定时事件。动画和 CPU 数据仍需要明确的时间事件，但不会通过轮询文件寻找按键。

## 使用

在仓库目录运行：

```shell
python -m pip install -e .
pixeldeck doctor
pixeldeck run buddy
```

默认只预览，不连接设备。左右方向键切换 demo，Enter 或空格操作。也可以用窗口按钮。

Windows 配对 MiniToo 后，填写自己的设备地址：

```shell
pixeldeck configure --address AA:BB:CC:DD:EE:FF
pixeldeck run pulse --send
```

手机需要释放屏幕控制连接。地址只是格式示例，本仓库不含真实设备配置。设置保存在用户目录的 `.pixeldeck` 中；`PIXELDECK_HOME` 可以指定其他私人运行目录。

启用机身媒体按键：

```shell
pixeldeck build-input
pixeldeck run buttons --send --media
```

这里会建立指定设备上的静音媒体会话。左右媒体操作切页，播放／暂停都对应一次操作。摇杆上、下、中央按下不属于已支持的输入。手机放歌与电脑显示并行需要单独验证。

## 七张小卡带

| 名称 | 内容 | 操作 |
|---|---|---|
| pulse | CPU 曲线、内存用量 | 冻结／恢复 |
| buddy | 像素小伙伴 | 打招呼、冒爱心 |
| rain | 霓虹字符雨 | 暂停／继续 |
| orbit | 星球、卫星和星空 | 暂停／继续 |
| focus | 一分钟像素沙漏 | 开始／暂停 |
| buttons | 按键计数诊断 | 每次加一 |
| signal | JSONL 推送通知 | 清空通知 |

图形预览见 [主 README](../README.md)。文档 GIF 是离线渲染，不代表蓝牙能达到同样帧率。硬件上传跟不上时会保留最新画面，而不是补播旧动画。

关闭窗口或运行 `pixeldeck stop` 停止。默认十分钟自动退出；`--duration 0` 可以取消时限，但设备长时间稳定性仍待验证。亮度控制和多帧 clip 属于实验接口，不会由普通 demo 自动调用。
