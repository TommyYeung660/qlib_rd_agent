# qlib_rd_agent 項目詳解

## 1. 項目定位與目標

**qlib_rd_agent** 是整個量化交易生態系統中的「**AI 研究員 (R&D Agent)**」。

它的核心任務是：**自動化挖掘交易因子 (Alpha Factors)**。

在您的量化架構中，它扮演著大腦的角色，負責思考和創新，而 `qlib_market_scanner` 則扮演眼睛和手腳的角色，負責執行和掃描。

---

## 2. 生態系統架構

本項目與外部系統的交互完全依賴 **Dropbox** 作為中轉站，實現了 Windows (Scanner) 與 WSL/Linux (RD-Agent) 的解耦。

### 角色分工

1.  **`qlib_market_scanner` (外部)**:
    *   **生產者**: 負責從數據源（如 Yahoo Finance, Binanace 等）下載原始市場數據。
    *   **轉換者**: 將原始數據轉換為 **Qlib Binary Format**（Qlib 專用的高效二進制格式）。
    *   **上傳者**: 將打包好的數據 (`qlib_binary.zip`) 上傳至 Dropbox。
    *   **消費者**: 等待 Dropbox 上出現新的因子文件，並將其納入掃描列表。

2.  **Dropbox (中轉)**:
    *   共享文件夾路徑：`/qlib_shared/`
    *   充當數據總線 (Data Bus)，傳遞數據快照和挖掘結果。

3.  **`qlib_rd_agent` (本項目)**:
    *   **下載者**: 從 Dropbox 拉取最新的市場數據。
    *   **挖掘者**: 運行微軟的 **RD-Agent** (基於 LLM 的研發代理)，利用 GPT-4o 等模型自動構建、測試、優化交易因子。
    *   **反饋者**: 將挖掘出的有效因子（如 `RSI + MACD` 的變體表達式）打包回傳至 Dropbox。

---

## 3. 詳細工作流程 (Workflow)

整個自動化流程分為三個標準步驟（對應 CLI 的 `full` 命令）：

### 步驟 1: 數據同步 (Sync)
*   **命令**: `python -m src.main sync`
*   **輸入**: Dropbox 上的 `/qlib_shared/qlib_binary.zip` 和 `manifest.json`。
*   **動作**:
    1.  檢查遠端 `manifest.json` 的時間戳，判斷是否有新數據。
    2.  下載壓縮包並解壓至本地 `data/qlib/` 目錄。
    3.  這確保了 RD-Agent 總是在最新的市場數據上進行挖掘。

### 2. 因子挖掘 (Run)
*   **命令**: `python -m src.main run`
*   **核心引擎**: Microsoft RD-Agent (`rdagent` 包)。
*   **動作**:
    1.  **環境準備**: 自動配置 Conda 環境 (`rdagent4qlib`) 和環境變量（API Keys）。
    2.  **路徑修復**: 由於 LLM 經常生成硬編碼路徑（如 `~/.qlib/qlib_data`），本項目會自動建立符號連結 (Symlinks) 指向真實數據，防止代碼報錯。
    3.  **啟動挖掘**: 
        *   LLM 提出因子假設（例如：「動量在波動率低時更有效」）。
        *   LLM 編寫 Python 代碼來實現該因子。
        *   Qlib 回測引擎在本地數據上運行該代碼，計算績效（IC, Sharpe Ratio）。
        *   LLM 根據回測結果進行自我反思和代碼修正。
    4.  **結果收集**: 挖掘結束後，系統會掃描工作目錄，提取出所有成功的因子定義。

### 3. 反饋上傳 (Feedback/Upload)
*   **命令**: `python -m src.main upload`
*   **輸出**: `discovered_factors.yaml`
*   **內容範例**:
    ```yaml
    factors:
      - name: "Volume_Weighted_Momentum"
        expression: "($close - Ref($close, 20)) / Ref($close, 20) * ($volume / Mean($volume, 20))"
        description: "由 AI 自動挖掘的成交量加權動量因子"
    ```
*   **動作**: 將此 YAML 文件上傳至 Dropbox 的 `/qlib_shared/rdagent_outputs/factors/`。

---

## 4. 給 `qlib_market_scanner` 的反饋是什麼？

您特別關心的「反饋」就是 **`discovered_factors.yaml`** 文件。

*   **本質**: 它是一份「藏寶圖」。
*   **作用**: 它告訴 `qlib_market_scanner`：「我發現了一個新的賺錢邏輯（因子），它的數學公式是 X，請開始監控符合這個邏輯的股票。」
*   **閉環**: 當 Scanner 讀取到這個文件後，就會在每日的市場掃描中加入這個新因子，從而實現從「數據」到「策略」的全自動化閉環。

## 5. 總結

**qlib_rd_agent** 是一個**無人值守的量化研發中心**。它不需要您手動編寫因子公式，而是讓 AI 閱讀最新的市場數據，自己去嘗試、報錯、修正，最後把驗證通過的獲利邏輯（因子）發送給您的交易終端 (Scanner)。
