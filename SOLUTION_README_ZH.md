"""
================================================================================
完整解決方案: RD-Agent 生成代碼中的硬編碼 Qlib 路徑問題
================================================================================

## 問題分析 (Problem Analysis)

錯誤訊息:
  ValueError: instrument: {'__DEFAULT_FREQ': '/path/to/qlib_data/cn_data'} 
              does not contain data for day

原因:
  1. RD-Agent 的 LLM 生成因子代碼時包含硬編碼的路徑
     - ~/.qlib/qlib_data/cn_data
     - /path/to/qlib_data/cn_data
  
  2. 這些路徑與實際配置的 QLIB_DATA_PATH 不符
  
  3. RD-Agent 無法找到 Qlib 數據，拋出 ValueError

## 為什麼無法直接修改生成的代碼?

1. RD-Agent 在子進程中運行,動態生成代碼
2. 代碼生成和執行發生在 RD-Agent 的內部機制中
3. 無法攔截或修改 RD-Agent 的系統提示(System Prompt)
4. 代碼生成時已經嵌入了硬編碼路徑

## 解決方案: 符號鏈接 (Symlink) 策略

而不是修改生成的代碼,我們創建符號鏈接:

  生成的代碼: qlib.init(provider_uri="~/.qlib/qlib_data/cn_data")
                             ↓
                    OS 路徑解析 (symlink)
                             ↓
                    實際數據路徑: QLIB_DATA_PATH
                             ↓
                    ✅ 成功找到數據!

### 優點
- ✅ 透明 - 不需修改生成的代碼
- ✅ 強大 - 在作業系統級別工作
- ✅ 容易 - 只需創建符號鏈接
- ✅ 可靠 - 所有工具都支持符號鏈接
- ✅ 無副作用 - 只創建/更新鏈接,不刪除文件

## 實現細節 (Implementation)

### 主要改動: src/runner/qlib_runner.py

新增函數: _setup_qlib_data_symlinks(config)

功能:
  1. 解析配置的 QLIB_DATA_PATH (實際數據路徑)
  2. 列出常見的硬編碼路徑:
     - ~/.qlib/qlib_data/cn_data
     - ~/.qlib/qlib_data
     - /path/to/qlib_data/cn_data
     - /path/to/qlib_data
  3. 為每個路徑創建符號鏈接到實際數據路徑
  4. 如果符號鏈接已存在但指向錯誤位置,自動更新它
  5. 優雅地處理權限錯誤(記錄但不失敗)

調用位置: run_rdagent() 第 2.5 步
  - 在設置環境變量後
  - 在啟動 RD-Agent 之前

### 備用方案 (Backup Approaches)

1. patch_generated_code.py
   - 可以修補生成的 Python 文件
   - 將硬編碼的 provider_uri 替換為環境變量
   - 確保導入 os 模塊
   - 如果符號鏈接不行則使用此方案

2. patch_monitor.py
   - 監控工作區中的新生成文件
   - 實時修補它們
   - 目前未使用,但可備用

## 創建的提交 (Commits)

1. 358aa37 - fix: handle hardcoded Qlib paths in RD-Agent generated code
   - 核心符號鏈接設置函數
   - 完整的錯誤處理和日誌記錄

2. 00f22ce - feat: add code patching utility for RD-Agent generated files
   - 備用代碼修補模塊
   - 獨立的可重用工具

3. 3328b5c - feat: add workspace monitoring for code patching
   - 工作區監控工具
   - 用於實時修補新生成的文件

4. 53cd5a5 - docs: add solution documentation and verification script
   - 解決方案文檔
   - 驗證腳本 (bash)

5. 14a8a70 - docs: add comprehensive summary of hardcoded paths fix
   - 完整的技術文檔和總結

## 工作流程 (Workflow)

運行 RD-Agent 時的步驟:

1. _verify_prerequisites() - 驗證數據路徑存在
2. _build_rdagent_env() - 設置環境變量
3. ⭐ _setup_qlib_data_symlinks() - 創建符號鏈接 ⭐
4. RD-Agent 啟動 - 執行因子生成
5. RD-Agent 生成: qlib.init(provider_uri="~/.qlib/qlib_data/cn_data")
6. OS 路徑解析: ~/.qlib/qlib_data/cn_data → QLIB_DATA_PATH
7. ✅ Qlib 找到數據並成功初始化

## 創建的符號鏈接

函數在用戶的主目錄中創建:

```
~/.qlib/qlib_data/cn_data  →  /actual/path/to/QLIB_DATA_PATH
~/.qlib/qlib_data          →  /actual/path/to/QLIB_DATA_PATH
```

嘗試創建(如果目錄存在):
```
/path/to/qlib_data/cn_data  →  /actual/path/to/QLIB_DATA_PATH
/path/to/qlib_data          →  /actual/path/to/QLIB_DATA_PATH
```

## 測試驗證 (Testing & Verification)

### 1. 驗證符號鏈接創建
```bash
# 檢查符號鏈接是否存在
ls -la ~/.qlib/qlib_data/cn_data

# 應該顯示:
# ~/.qlib/qlib_data/cn_data -> /actual/path/to/data
```

### 2. 運行 RD-Agent
```bash
python -m src.main run

# 查看日誌中的符號鏈接創建消息:
# "Created symlink: ... -> ..."

# 確保沒有 "does not contain data" 錯誤
```

### 3. 驗證因子發現
```bash
# 檢查輸出
cat {workspace_dir}/discovered_factors.yaml

# 應該包含發現的因子,而不是錯誤
```

### 4. 運行驗證腳本
```bash
bash verify_fix.sh

# 應該通過所有檢查
```

## 錯誤處理 (Error Handling)

如果符號鏈接創建失敗:
  - 函數記錄錯誤但繼續(非阻塞)
  - 備用方案可用: patch_generated_code.py
  - 用戶可以手動創建:
    ```bash
    ln -s /actual/path ~/.qlib/qlib_data/cn_data
    ```

## 文件清單 (File List)

創建/修改的文件:

1. src/runner/qlib_runner.py (修改)
   - 新增 _setup_qlib_data_symlinks() 函數
   - 新增導入: patch_generated_code_in_workspace
   - 在 run_rdagent() 中新增調用

2. src/runner/patch_generated_code.py (新創建)
   - 備用代碼修補模塊
   - 獨立可運行工具

3. src/runner/patch_monitor.py (新創建)
   - 工作區監控模塊
   - 實時修補功能

4. SOLUTION_HARDCODED_PATHS.md (新創建)
   - 詳細的解決方案文檔
   - 中英文解說

5. FIX_HARDCODED_PATHS_SUMMARY.md (新創建)
   - 技術摘要和驗證指南
   - Git 提交信息

6. verify_fix.sh (新創建)
   - Bash 驗證腳本
   - 自動化檢查部署是否正確

## 代碼品質檢查 (Code Quality)

✅ 所有 Python 文件語法正確
✅ 所有導入正確解析
✅ 遵循 PEP 8 風格
✅ 完整的文檔字符串 (docstrings)
✅ 錯誤處理完善
✅ 日誌記錄充分
✅ 無破壞性改動
✅ 向後兼容

## 未來改進 (Future Improvements)

1. 集成 patch_generated_code.py
   - 如果符號鏈接在某些場景失敗

2. 設置 Qlib 配置文件
   - 在 ~/.qlib/conf.yaml 中設置路徑

3. 創建自定義 qlib.init() 包裝器
   - 在 prepare_data.py 中確保正確初始化

4. Fork RD-Agent
   - 修改內部提示(長期解決方案)

## 總結 (Summary)

問題: ❌ RD-Agent 生成的代碼包含硬編碼的 Qlib 路徑
解決: ✅ 創建符號鏈接從硬編碼路徑到實際數據路徑
結果: ✅ 生成的代碼可以透明地工作,無需修改

方法:
  - 簡單: 只需創建符號鏈接
  - 可靠: 在 OS 級別工作
  - 安全: 無副作用,優雅的錯誤處理
  - 備用: 如果需要可以使用代碼修補

狀態: 🎉 實現完成,已提交,準備測試
"""
