# Plusone 固件说明

这是 [78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) **v2.2.6** 的定制版，只给一块板子用：
**M5Stack AtomS3R + Atomic Echo Base**（玩偶里那块）。其他板子没动过，也没测过。

## 改了什么

| 改动 | 官方固件 | 我们的固件 | 改哪里 |
| --- | --- | --- | --- |
| 唤醒词 | 「你好小智」（WakeNet 固定模型） | 「你好牛牛」（MultiNet 自定义唤醒词，拼音 `ni hao niu niu`） | `main/boards/atoms3r-echo-base/config.json` |
| 配网热点名 | `Xiaozhi-XXXX` | `NiuNiu-XXXX` | 同上，`CONFIG_WIFI_CONFIG_SSID_PREFIX` |
| 默认服务器（OTA 地址） | 小智官方服务器 | 我们自己的服务器，**编译时从私有文件读，不进仓库** | `scripts/plusone_build.py` |
| 分区表 | `8m.csv`：两个 3MB 程序区 + 2MB 资源区 | `8m_plusone.csv`：一个 3MB 程序区 + 5MB 资源区 | `partitions/v2/8m_plusone.csv` |

### 为什么改分区表

自定义唤醒词要用中文 MultiNet7 模型（`mn7_cn`，约 2.6MB），原来的资源区只有 2MB，放不下。
所以去掉了第二个程序区，把空间让给资源区。

代价：**不能再通过服务器远程推送新固件（空中升级）**，以后换固件都要插 USB 线烧。
连服务器、拿配置、聊天这些都不受影响。

### 唤醒词怎么改

所有相关设置都在 `main/boards/atoms3r-echo-base/config.json` 一个文件里：

```json
"CONFIG_CUSTOM_WAKE_WORD=\"ni hao niu niu\"",   // 拼音，字之间空格隔开，不带声调
"CONFIG_CUSTOM_WAKE_WORD_DISPLAY=\"你好牛牛\"",   // 唤醒后发给服务器、屏幕上显示的字
"CONFIG_CUSTOM_WAKE_WORD_THRESHOLD=20",         // 1–99，越小越灵敏，默认 20
"CONFIG_WIFI_CONFIG_SSID_PREFIX=\"NiuNiu\"",     // 配网热点名前缀
```

改完重新编译、烧录即可。

**灵敏度**：如果实际用下来经常误触发（没叫它它自己醒），把 `CONFIG_CUSTOM_WAKE_WORD_THRESHOLD`
调高一点（比如 30、40）；如果叫了好几遍都叫不醒，就调低一点（比如 10、15）。每次改完重新编译烧录试。

## 怎么编译

### 第一次：装 ESP-IDF v5.5.2

```bash
mkdir -p ~/esp && cd ~/esp
git clone -b v5.5.2 --recursive https://github.com/espressif/esp-idf.git esp-idf-v5.5.2
cd esp-idf-v5.5.2 && ./install.sh esp32s3
```

### 每次编译

```bash
. ~/esp/esp-idf-v5.5.2/export.sh       # 进入 ESP-IDF 环境（每开一个新终端都要做一次）
cd plusone-firmware
python scripts/plusone_build.py
```

脚本会自己找服务器地址，按下面顺序，找到一个就用：

1. 命令行参数：`--ota-url https://你的域名/plusone/ota/`
2. 环境变量：`PLUSONE_OTA_URL=https://你的域名/plusone/ota/`
3. 仓库根目录的 `plusone.local.env`（已加进 `.gitignore`，不会被提交），写一行
   `PLUSONE_HOST=你的域名` 或 `PLUSONE_OTA_URL=https://…/plusone/ota/`
4. 旁边 Plusone 项目的 `../Plusone/private/deploy.env` 里的 `PLUSONE_HOST`
   （地址会拼成 `https://<PLUSONE_HOST>/plusone/ota/`）

都找不到就直接报错，不会悄悄用小智官方服务器。
终端里打印的地址会把域名遮成 `***`，截图或贴日志不会泄露。

编译完会打印程序和资源各占分区的多少，超了会报错。产物在 `build/` 下：
`build/merged-binary.bin` 是一整片的镜像。

> 地址只会写进 `sdkconfig` 和 `build/`，两者都在 `.gitignore` 里。**不要**手动把地址写进
> `config.json`、`sdkconfig.defaults` 或其他会提交的文件。

## 怎么烧录

1. 用 USB-C 线把 AtomS3R 接到电脑。
2. 找端口：`ls /dev/cu.usbmodem*`
3. 烧录（在 ESP-IDF 环境里，仓库根目录）：

   ```bash
   idf.py -p /dev/cu.usbmodemXXXX flash
   ```

   这一步会把引导程序、新分区表、程序和资源（含唤醒词模型）一起写进去。
   看串口日志：`idf.py -p /dev/cu.usbmodemXXXX monitor`（退出按 `Ctrl+]`）。

如果烧完开不了机或一直重启，先整片擦除再烧一次（会清掉保存的 Wi-Fi，需要重新配网）：

```bash
idf.py -p /dev/cu.usbmodemXXXX erase-flash
idf.py -p /dev/cu.usbmodemXXXX flash
```

如果电脑认不到板子：按住 AtomS3R 侧面的复位键约 2 秒，直到内部绿灯亮，进入下载模式后再烧。

## 怎么换回官方固件

用 M5Stack 官方的 **M5Burner**：

1. 打开 M5Burner，左边选 **ATOMS3R**（或搜 XiaoZhi），找到 Echo Base 的 **XiaoZhi** 固件（我们原来用的是 v2.2.6）。
2. 点 Download，再点 Burn，选对端口，开始烧录。
3. M5Burner 写的是整片镜像，会把官方的分区表一起写回去，烧完就是原来的样子。

回到官方固件后，唤醒词变回「你好小智」，连的是小智官方服务器（要重新在设备里配置我们服务器的话，跟以前一样）。
