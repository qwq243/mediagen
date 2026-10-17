# 独立视觉复核提示词与回执

```text
你是独立复核者，不是原标注者。重新打开manifest中的全部原图，不能只读JSON、
摘要、OCR或带框预览。确认原图sha256与source.version。
检查每页：关键元素漏标、原图归一化坐标、content_box、父子引用、准确文案、
字体名称证据、取色方法、箭头端点与方向、播放器/广告污染、真实证据保护、
使用与上传权限。对不可读细节放大查看；仍不清晰则写unknown，不补造。
检查作品层主题是否被混合来源污染，近重复页和库内顺序是否被误当作者叙事。
每条缺陷必须定位page_id、element_id和具体字段，给原图依据，退回修改。
初步盘点或遗漏关键原子不能通过；字段完整或JSON可解析不等于视觉审核通过。
当前64页中56页仍为coverage.complete=false，8页是详细候选；两者都不能直接改为reviewed。
在独立查看的证据、所有检查通过且coverage.complete=true时才出reviewed回执。
否则rejected并列具体问题。不改原作者标签，不覆盖旧图，不执行生图。
```

回执按单页保存；`annotation_hash`取知识库详情当前值，reviewer不得与annotator相同：

```json
{
  "asset_id": "a-实际ID",
  "version": "manifest中的图片版本",
  "annotation_hash": "待审核候选JSON的规范化哈希",
  "source_sha256": "原图字节哈希",
  "reviewer": "独立复核者标识",
  "status": "rejected",
  "visual_evidence": ["实际打开的原图及局部位置、复核时间、记录路径"],
  "checks": {
    "coverage": "failed",
    "coordinates": "pending",
    "text": "pending",
    "font_evidence": "pending",
    "relations": "pending",
    "contamination": "pending",
    "rights": "pending"
  },
  "findings": [
    {"page_id": "PG-实际ID", "element_id": "e01", "field": "children",
     "issue": "此复杂卡片仍包含未单独标注的正文和图标", "evidence": "原图具体位置"}
  ]
}
```

入库器检查候选哈希、原图哈希、不同复核者、完整覆盖与全部检查状态。
它无法代替真正看图；禁止生成虚假的visual_evidence来绕过门槛。
