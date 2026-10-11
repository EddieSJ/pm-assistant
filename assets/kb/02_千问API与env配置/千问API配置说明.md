# 千问API与环境变量配置说明

## 配置目的

本课程要求通过API调用模型，而不是只在聊天页面中问答。API Key应当写入本地环境文件，由程序读取，不得直接写入代码、截图、或共享群。

## 基本配置

- 中国内地兼容模式地址：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- 环境变量名称：`DASHSCOPE_API_KEY`
- 课程默认模型占位：`qwen-plus`

请以当期账号权限和阿里云百炼官方说明为准：

- https://help.aliyun.com/zh/model-studio/get-api-key/
- https://help.aliyun.com/zh/model-studio/base-url
- https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions

## 操作步骤

1. 复制 `.env.example` 为 `.env`。
2. 只在本地 `.env` 中填写Key。
3. 运行连接测试，记录模型名、成功时间和请求编号，不记录完整Key。
4. 连接成功后再加载知识库、约束、任务记忆和项目输入资料。
5. 提交前检查 `.env`、日志、截图和代码，确认没有真实Key。

## 安全要求

- 一旦怀疑Key泄露，立即轮换Key。
- 不把含Key的文件上传到代码仓库、网盘或课程群。
- 财务、合同和人员资料的输出必须人工复核。
- `AGENT_REQUIRE_HUMAN_APPROVAL=true` 表示Agent只能准备草稿和整理结果，不能自动外发或审批。
