/* mediagen adapter for PPT Master v6.7.0 (MIT, Hugo He).
 * The upstream controls and layout remain in app.js/style.css.
 * These additions never call an image model or silently approve a proposal.
 */
(function () {
    "use strict";
    var draft, revision, materialEdited = false, pendingDirection;
    var nativeFetch = window.fetch.bind(window);
    window.fetch = function (url, options) {
        options = options || {};
        if ((options.method || "GET").toUpperCase() === "GET") return nativeFetch(url, options);
        return nativeFetch("/api/session").then(function (r) { return r.json(); }).then(function (s) {
            options.headers = Object.assign({}, options.headers || {}, {"X-Mediagen-CSRF": s.csrf});
            return nativeFetch(url, options);
        });
    };
    function node(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text != null) n.textContent = text;
        return n;
    }
    function block(host, title, description) {
        var n = node("section", "section mg-section");
        n.appendChild(node("h2", "section-title", title));
        if (description) n.appendChild(node("p", "section-note", description));
        host.appendChild(n);
        return n;
    }
    function field(host, label, value, change, multi) {
        var wrap = node("label", "mg-field");
        wrap.appendChild(node("span", "", label));
        var input = node(multi ? "textarea" : "input");
        input.value = value == null ? "" : value;
        if (multi) input.rows = 3;
        input.addEventListener("input", function () { change(input.value); });
        wrap.appendChild(input); host.appendChild(wrap); return input;
    }
    function select(host, label, choices, value, change) {
        var wrap = node("label", "mg-field");
        wrap.appendChild(node("span", "", label));
        var s = node("select");
        choices.forEach(function (x) { var o = node("option", "", x[1]); o.value = x[0]; s.appendChild(o); });
        s.value = value;
        s.addEventListener("change", function () { change(s.value); });
        wrap.appendChild(s); host.appendChild(wrap); return s;
    }
    function button(host, text, action) {
        var b = node("button", "mg-button", text); b.type = "button";
        b.addEventListener("click", action); host.appendChild(b); return b;
    }
    function link(host, label, url) {
        if (!/^https?:\/\//i.test(url)) return;
        var a = node("a", "mg-link", label); a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer";
        host.appendChild(a);
    }
    function post(url, data, status) {
        return window.fetch(url, {method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data)}).then(function (r) {
                return r.json().then(function (v) {
                    if (!r.ok) throw new Error(v.error || "提交失败");
                    status.textContent = "已记录。"; return v;
                });
            }).catch(function (e) { status.textContent = e.message; });
    }
    window.mediagenPayload = function (payload, rec) {
        if (payload.stage === "final") payload.stage = "stage2";
        payload._source_hash = rec.mediagen.source_hash;
        payload.mediagen_choices = {
            communication: {
                organization: draft.communication.organization,
                organization_rationale: draft.communication.organization_rationale,
                reading_mode: draft.communication.reading_mode,
                duration_seconds: draft.communication.duration_seconds
            }, pages: draft.pages,
            human_policy: draft.design.human_policy, display: draft.design.typography.display,
            grid: draft.design.grid,
            notes_policy: draft.notes_policy, transition: draft.transition, references: draft.references
        };
        if (materialEdited) payload.mediagen_choices.material = draft.design.material;
        return payload;
    };
    window.mediagenApplyDirection = function (candidate) {
        pendingDirection = candidate;
        if (draft && candidate.display_font) draft.design.typography.display = candidate.display_font;
        if (draft && candidate.image_strategy) {
            draft.design.material = candidate.image_strategy.behavior || candidate.image_strategy.rendering;
            materialEdited = false;
        }
    };
    window.mediagenRender = function (host, stage, rec) {
        if (!rec.mediagen) return;
        if (!draft || revision !== rec.mediagen.source_hash) {
            draft = JSON.parse(JSON.stringify(rec.mediagen.pack)); revision = rec.mediagen.source_hash;
            materialEdited = false;
            if (pendingDirection && pendingDirection.display_font) {
                draft.design.typography.display = pendingDirection.display_font;
            }
        }
        var head = document.querySelector("h1");
        if (head) head.textContent = "Mediagen · 图片型 PPT 设计确认";
        var hint = document.getElementById("topbar-hint");
        if (hint) hint.textContent = (draft.project_name || "当前 PPT") +
            (draft.retrospective_only ? " · 历史案例复盘，不会启动生产" : " · 推荐待确认，不会自动生图");
        if (draft.retrospective_only) {
            block(host, "历史案例：只复盘，不自动重生成",
                "旧图仅作为参考；这里是尚未批准的改进建议，不追认历史审核。确认设计不会收费或启动生成；实际制作须另建授权任务。");
        }
        if (stage === 1) {
            var previewHost = document.getElementById("topbar-preview");
            if (previewHost) {
                var overview = block(previewHost, "先讲清楚，再做设计", "第一阶段是未确认的内容提案；第二阶段再看色卡、字体和设计候选。");
                overview.appendChild(node("p", "section-note", "组织方式：" + draft.communication.organization));
                overview.appendChild(node("p", "section-note", draft.pages.length + " 页 · PPT 段预算：" +
                    (draft.communication.duration_seconds == null ? "待确认" : draft.communication.duration_seconds + " 秒")));
                var outline = node("ol", "mg-outline");
                draft.pages.forEach(function (pg) {
                    outline.appendChild(node("li", "", pg.page_id + " · " +
                        (pg.logic.key_message_or_question || pg.logic.purpose || "待补充展示逻辑")));
                });
                overview.appendChild(outline);
            }
            var logic = block(host, "沟通蓝图与逐页逻辑", "推荐不是确认。组织逻辑可混合、可自定义；先说明信息关系，再选择几何布局。");
            field(logic, "整套组织方式（论证／故事／教学／决策／机制／进展／混合）",
                draft.communication.organization, function (v) { draft.communication.organization = v; });
            field(logic, "为什么这样组织", draft.communication.organization_rationale,
                function (v) { draft.communication.organization_rationale = v; }, true);
            select(logic, "观看方式／文字量依据", [["presentation", "现场讲述"], ["text", "独立阅读"], ["balanced", "兼顾两者"]],
                draft.communication.reading_mode, function (v) { draft.communication.reading_mode = v; });
            field(logic, "PPT 讲述时间预算（秒；不包含演示与答辩）", draft.communication.duration_seconds,
                function (v) { draft.communication.duration_seconds = v ? Number(v) : null; });
            draft.pages.forEach(function (p) {
                var details = node("details", "mg-page"); details.open = draft.pages.length < 4;
                details.appendChild(node("summary", "", p.page_id + " · " + (p.page_role || "内容页")));
                var grid = node("div", "mg-grid");
                [["purpose", "目的"], ["key_message_or_question", "关键结论或问题"],
                    ["information_relationship", "信息关系（因果／顺序／对照／层级等）"],
                    ["visual_expression", "视觉表达"], ["transition_in", "接上页"], ["transition_out", "引下页"]]
                    .forEach(function (x) { field(grid, x[1], p.logic[x[0]], function (v) { p.logic[x[0]] = v; }, true); });
                field(grid, "支撑证据（逐行输入；没有证据需说明边界）", (p.logic.evidence || []).join("\n"),
                    function (v) { p.logic.evidence = v.split("\n").filter(Boolean); }, true);
                field(grid, "预计讲述秒数", p.logic.duration_seconds,
                    function (v) { p.logic.duration_seconds = v ? Number(v) : null; });
                details.appendChild(grid);
                field(details, "页面可见文字（讲稿另存，不会送入生图）", p.page_text,
                    function (v) { p.page_text = v; }, true);
                logic.appendChild(details);
            });
        } else {
            var policy = block(host, "图片型制作选择", "文字默认直接生成在图中；网页字体和版式是示意，真实模型样张需要另行确认。");
            select(policy, "是否允许人物", [["none", "不出现人物（默认）"], ["illustrated", "仅插画人物"],
                ["real_photos", "仅用户授权真实照片"], ["generated_realistic", "允许生成写实人物"]],
                draft.design.human_policy, function (v) { draft.design.human_policy = v; });
            var displaySample = node("p", "mg-display-sample", "见微知著 · Design");
            displaySample.style.fontFamily = draft.design.typography.display;
            field(policy, "封面／章节展示字体（允许艺术字）", draft.design.typography.display,
                function (v) { draft.design.typography.display = v; displaySample.style.fontFamily = v; });
            policy.appendChild(displaySample);
            field(policy, "网格与安全边距", draft.design.grid, function (v) { draft.design.grid = v; });
            field(policy, "材质语言（补充覆盖；留用原值则以上方生成图风格为准）", draft.design.material,
                function (v) { draft.design.material = v; materialEdited = true; });
            select(policy, "AI 讲稿", [["generate", "生成分页讲稿（默认）"], ["optimize", "优化现有原稿"],
                ["preserve", "逐字保留原稿"], ["off", "不需要讲稿"]],
                draft.notes_policy.enabled ? draft.notes_policy.mode : "off", function (v) {
                    draft.notes_policy = {enabled: v !== "off", mode: v === "off" ? "generate" : v, audio: false};
                });
            var motion = block(host, "翻页转场（可选）", "仅整页切换，不是图中文字逐条动画；手动翻页、无声音。下面只是浏览器示意。");
            var preview = node("div", "mg-motion", "章节 A → 章节 B"); motion.appendChild(preview);
            select(motion, "是否需要转场", [["off", "不需要（默认）"], ["on", "需要"]],
                draft.transition.enabled ? "on" : "off", function (v) { draft.transition.enabled = v === "on"; });
            select(motion, "转场类型", [["fade", "淡化（推荐）"], ["push", "推入"], ["wipe", "擦除"],
                ["split", "分割"], ["cover", "覆盖"]], draft.transition.effect, function (v) { draft.transition.effect = v; });
            field(motion, "时长（秒）", draft.transition.duration, function (v) { draft.transition.duration = Number(v); });
            button(motion, "播放转场示意", function () {
                var dx = draft.transition.effect === "push" || draft.transition.effect === "cover" ? 100 : 0;
                preview.animate([{opacity: 0, transform: "translateX(" + dx + "px)"},
                    {opacity: 1, transform: "translateX(0)"}], {duration: draft.transition.duration * 1000});
            });
            var individual = node("details", "mg-page");
            individual.appendChild(node("summary", "", "逐页转场（可继承、关闭或单独设置）"));
            draft.pages.forEach(function (pg) {
                var row = node("div", "mg-grid");
                var mode = select(row, pg.page_id + " 转场", [["inherit", "继承全套"], ["off", "关闭本页"], ["on", "单独设置"]],
                    !pg.transition ? "inherit" : pg.transition.enabled === false ? "off" : "on", function (v) {
                        if (v === "inherit") delete pg.transition;
                        else pg.transition = Object.assign({}, draft.transition, pg.transition || {}, {enabled: v === "on"});
                    });
                function override(key, value) {
                    pg.transition = Object.assign({}, draft.transition, pg.transition || {}, {enabled: true});
                    pg.transition[key] = value; mode.value = "on";
                }
                select(row, pg.page_id + " 类型", [["fade", "淡化"], ["push", "推入"], ["wipe", "擦除"],
                    ["split", "分割"], ["cover", "覆盖"]], (pg.transition || draft.transition).effect,
                    function (v) { override("effect", v); });
                field(row, pg.page_id + " 秒数", (pg.transition || draft.transition).duration,
                    function (v) { override("duration", Number(v)); });
                individual.appendChild(row);
            });
            motion.appendChild(individual);
        }
        var sources = block(host, "参考库与补充素材", "可自行浏览网站，把喜欢的链接、截图、PPT、图片或文字带回来。参考风格不等于有权复制素材；上传图像模型默认不授权。新本地路径先登记，agent核验并导入后才能预览／上传。");
        rec.mediagen.sites.forEach(function (s) { link(sources, s.name, s.url); });
        if (stage === 1) sources.appendChild(node("p", "section-note", "本阶段先确认故事和内容；下一阶段可登记参考并选择制作政策。"));
        if (stage === 2) {
            var library = rec.mediagen.library || [];
            if (library.length) {
                select(sources, "选择共享库参考", [["", "请选择"]].concat(library.map(function (r) {
                    return [r.id, r.payload.title || r.payload.name || r.id];
                })), "", function (id) {
                    var r = library.find(function (x) { return x.id === id; });
                    if (!r) return;
                    var item = JSON.parse(JSON.stringify(r.payload));
                    item.id = "library-" + id.slice(0, 10); item.send_to_model = false;
                    if (!draft.references.some(function (x) { return x.id === item.id; })) draft.references.push(item);
                    window.mediagenRenderRefresh();
                });
            }
            var form = node("div", "mg-grid"), entry = {};
            field(form, "参考标题", "", function (v) { entry.title = v; });
            field(form, "网址（也支持你回来提供的链接）", "", function (v) { entry.url = v; });
            field(form, "本地素材绝对路径（可留空）", "", function (v) { entry.path = v; });
            field(form, "用途／喜欢哪里／不喜欢哪里", "", function (v) { entry.use = v; }, true);
            field(form, "权利或许可说明", "", function (v) { entry.license = v; });
            select(form, "素材职责", [["style", "视觉风格"], ["content", "内容参考"], ["evidence", "真实证据，禁止重画"]],
                "style", function (v) { entry.role = v; });
            select(form, "图像模型上传权限", [["no", "不授权（默认）"], ["yes", "授权此素材作为参考上传"]],
                "no", function (v) { entry.upload_allowed = v === "yes"; entry.send_to_model = v === "yes"; });
            sources.appendChild(form);
            button(sources, "登记到本次设计草稿", function () {
                if (!entry.url && !entry.path) return;
                draft.references.push(Object.assign({id: "user-" + Date.now(), role: "style",
                    license: "pending", preserve: true, redraw_allowed: false,
                    upload_allowed: false, send_to_model: false}, entry));
                window.mediagenRenderRefresh();
            });
        }
        draft.references.forEach(function (r) {
            var card = node("div", "mg-reference");
            card.appendChild(node("strong", "", (r.title || r.id) + " · " + r.role));
            card.appendChild(node("p", "", (r.use || "") + " · 许可：" + (r.license || "待确认")));
            if (r.requested_path) card.appendChild(node("p", "mg-status", "待核验本地素材：" + r.requested_path));
            if (r.url) link(card, "打开来源", r.url);
            if (r.path && /\.(png|jpe?g|webp|svg)$/i.test(r.path) &&
                rec.mediagen.pack.references.some(function (saved) { return saved.id === r.id; })) {
                var img = node("img", "mg-thumbnail"); img.src = "/api/image/ref-" + encodeURIComponent(r.id);
                img.alt = "素材参考，不是生成样张"; card.appendChild(img);
            }
            sources.appendChild(card);
        });
        if (rec.mediagen.history && rec.mediagen.history.length) {
            var history = block(host, "相关偏好与历史问题", "这是可检索的经验，不是自动套用的全局硬规则；以记录的适用范围和本次确认优先。");
            rec.mediagen.history.forEach(function (record) {
                var item = record.payload;
                history.appendChild(node("p", "section-note", record.kind + " · " +
                    (item.description || item.comment || item.title || record.id) +
                    " · 范围：" + (item.scope || "待说明") + " · 状态：" + (item.status || "待反馈")));
            });
        }
        if (stage === 2) {
            var samples = block(host, "真实样张与后续审核", "封面＋代表性内容页先审后确认；未生成时不拿设计示意冒充。网页不会自动生成或收费。");
            var ready = true;
            rec.mediagen.sample_page_ids.forEach(function (id) {
                var p = draft.pages.find(function (x) { return x.page_id === id; });
                var selected = p && p.selected_output;
                var card = node("div", "mg-reference");
                card.appendChild(node("strong", "", id));
                if (selected) {
                    var img = node("img", "mg-slide"); img.src = "/api/image/" + encodeURIComponent(id);
                    img.alt = id + " · " + selected.kind; card.appendChild(img);
                    card.appendChild(node("p", "", "产物类别：" + selected.kind + "；来源：" + selected.provenance));
                } else {
                    ready = false; card.appendChild(node("p", "", "尚无实际生成样张"));
                }
                samples.appendChild(card);
            });
            var status = node("p", "mg-status"); samples.appendChild(status);
            button(samples, "刷新样张与审核状态", function () { window.location.reload(); });
            var approve = button(samples, "确认这组实际样张", function () {
                post("/api/sample-confirm", {subject_hash: rec.mediagen.sample_subject_hash}, status);
            });
            approve.disabled = !ready || !rec.mediagen.stage2_confirmed || !rec.mediagen.sample_ready;
            if (rec.mediagen.sample_blockers && rec.mediagen.sample_blockers.length) {
                samples.appendChild(node("p", "mg-status", "样张确认未开放：" + rec.mediagen.sample_blockers.join("；")));
            }
            samples.appendChild(node("p", "section-note", "以下为已保存版本的有效审核状态；尚未提交的编辑不算已审核。"));
            var audits = node("pre", "mg-audits", JSON.stringify(rec.mediagen.audit_states || {}, null, 2));
            samples.appendChild(audits);
            var feedback = block(host, "使用评价与改进建议", "尚未使用可暂不评价。建议分别说视觉、逻辑、文字量、讲稿、动效；单次反馈不会自动变成全局规则。");
            var note = "", scope = "this_project", type = "comment", dimension = "visual";
            field(feedback, "评价／偏好／具体问题", "", function (v) { note = v; }, true);
            select(feedback, "反馈类型", [["comment", "一般评价"], ["preferences", "个人偏好"],
                ["issues", "具体缺陷"], ["lessons", "候选经验"]], type, function (v) { type = v; });
            select(feedback, "评价维度", [["visual", "视觉／风格"], ["logic", "展示逻辑"], ["typography", "字体"],
                ["density", "文字量"], ["notes", "讲稿"], ["motion", "动效"], ["other", "其他"]],
                dimension, function (v) { dimension = v; });
            select(feedback, "适用范围", [["this_project", "本次 PPT"], ["similar_projects", "同类场景"],
                ["all_ppt", "所有 PPT（我明确希望如此）"]], scope, function (v) { scope = v; });
            var saved = node("p", "mg-status"); feedback.appendChild(saved);
            button(feedback, "记录评价", function () {
                var value = {comment: note, scope: scope};
                if (type !== "comment") value[type] = [{description: note, dimension: dimension,
                    status: type === "issues" ? "open" : "candidate"}];
                post("/api/feedback", value, saved);
            });
        }
    };
    // Hook assigned by the retained upstream renderer.
    if (typeof window.mediagenRenderRefresh !== "function") window.mediagenRenderRefresh = function () {};
}());
