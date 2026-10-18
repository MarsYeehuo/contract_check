import { readFile } from "node:fs/promises";

import { chromium } from "playwright-core";

const base = process.env.FRONTEND_URL || "http://127.0.0.1:5173";
const channel = process.env.BROWSER_CHANNEL || "msedge";
const screenshotPath = process.env.SCREENSHOT_PATH;

const health = await fetch(`${base}/health`).catch(() => null);
if (!health || !health.ok) {
  console.error(
    `无法访问 ${base}/health。请先启动后端（8000）和前端开发服务器（5173）。`,
  );
  process.exit(1);
}
const healthPayload = await health.json().catch(() => ({}));
const serverConfigured = Boolean(healthPayload.llm_configured);

function assert(condition, message) {
  if (!condition) {
    throw new Error(`断言失败：${message}`);
  }
  console.log(`PASS ${message}`);
}

const browser = await chromium.launch({ channel, headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
page.setDefaultTimeout(20_000);

try {
  await page.goto(base);
  await page.getByRole("heading", { name: "合同初审工作台" }).waitFor();
  assert(true, "首页标题可见");

  const sampleButton = page.getByRole("button", { name: /含 2 处风险/ });
  await sampleButton.waitFor();
  await sampleButton.click();
  await page.waitForFunction(() => {
    const input = document.querySelector("textarea");
    return input !== null && input.value.includes("技术服务合同");
  });
  assert(true, "样例文本已载入");

  await page.getByRole("button", { name: "开始审查" }).click();
  await page.getByRole("heading", { name: "审查摘要" }).waitFor();

  assert((await page.locator(".rule-card").count()) === 6, "显示 6 条规则卡片");
  const summary = await page.locator(".summary-counts").innerText();
  assert(summary.includes("通过 3"), "摘要通过数为 3");
  assert(summary.includes("风险 2"), "摘要风险数为 2");
  assert(summary.includes("需人工确认 1"), "摘要待确认数为 1");

  assert(
    (await page.locator(".contract-text mark").count()) > 0,
    "默认风险规则证据已高亮",
  );
  const penaltyCard = page.locator(".rule-card", {
    hasText: "违约金比例上限",
  });
  await penaltyCard.locator(".evidence-link").first().click();
  await page.locator("#ev-penalty_ratio-0.flash").waitFor();
  assert(true, "点击证据后定位并闪烁");

  await page.getByRole("button", { name: "AI 设置" }).click();
  const aiDialog = page.getByRole("dialog", { name: "AI 兜底设置" });
  await aiDialog.waitFor();
  assert(
    await aiDialog
      .getByText(serverConfigured ? "服务端已配置 Key" : "服务端未配置 Key")
      .isVisible(),
    "AI 设置显示服务端 Key 状态",
  );
  await aiDialog.getByRole("button", { name: "关闭" }).click();
  assert(!(await aiDialog.isVisible()), "AI 设置弹窗可关闭");

  const ipCard = page.locator(".rule-card", { hasText: "知识产权归属" });
  if (!serverConfigured) {
    await page.locator(".mock-ai-banner").waitFor();
    assert(
      (await page.locator(".mock-ai-banner").innerText()).includes(
        "前端本地模拟",
      ),
      "未配置 Key 时显示模拟提示",
    );
    assert(
      (await page.locator(".summary-footer").innerText()).includes(
        "前端模拟 1 条",
      ),
      "摘要显示前端模拟数量",
    );
    const ipAi = ipCard.locator(".ai-block");
    await ipAi.waitFor();
    const ipAiText = await ipAi.innerText();
    assert(
      ipAiText.includes("前端模拟") && ipAiText.includes("需人工复核"),
      "未命中规则显示模拟 AI 判断",
    );
  }
  await ipCard.locator("select").selectOption("pass");
  await ipCard.locator('input[placeholder*="可选"]').fill("E2E 补充条款");
  await ipCard.getByRole("button", { name: "保存结论" }).click();
  await page.getByText("结论已保存，已记录审计").waitFor();

  assert(await ipCard.getByText("已人工覆盖").isVisible(), "卡片显示已人工覆盖");
  assert(
    (await ipCard.innerText()).includes("E2E 补充条款"),
    "卡片显示人工备注",
  );
  assert(
    (await page.locator(".summary-footer").innerText()).includes(
      "已人工标注 1 条",
    ),
    "摘要显示已人工标注数量",
  );

  await page.getByRole("button", { name: /查看审计/ }).click();
  const drawer = page.locator(".drawer");
  await drawer.getByRole("heading", { name: "审计记录" }).waitFor();
  await drawer.locator(".audit-item").first().waitFor();
  assert(
    (await drawer.locator(".audit-item").count()) === 1,
    "审计抽屉显示 1 条记录",
  );
  const auditText = await drawer.innerText();
  assert(
    auditText.includes("知识产权归属") &&
      auditText.includes("E2E 补充条款") &&
      auditText.includes("演示审核员"),
    "审计包含规则、备注与审核人",
  );
  await drawer.getByRole("button", { name: "关闭" }).click();
  assert(!(await drawer.isVisible()), "审计抽屉可关闭");

  if (!serverConfigured) {
    assert(
      (await page.locator(".export-bar").innerText()).includes(
        "AI 模拟结果不入报告",
      ),
      "导出栏提示模拟结果不入报告",
    );
  }

  const dialogs = [];
  page.on("dialog", async (dialog) => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  const [markdownDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "导出 Markdown" }).click(),
  ]);
  const markdownName = markdownDownload.suggestedFilename();
  assert(markdownName.endsWith(".md"), `Markdown 文件名：${markdownName}`);
  const markdownPath = await markdownDownload.path();
  assert(markdownPath !== null, "Markdown 下载已落地");
  const markdownContent = await readFile(markdownPath, "utf8");
  assert(
    markdownContent.includes("人工修改审计") &&
      markdownContent.includes("E2E 补充条款"),
    "Markdown 报告包含审计与备注",
  );

  const [jsonDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "导出 JSON" }).click(),
  ]);
  const jsonName = jsonDownload.suggestedFilename();
  assert(jsonName.endsWith(".json"), `JSON 文件名：${jsonName}`);
  const jsonPath = await jsonDownload.path();
  assert(jsonPath !== null, "JSON 下载已落地");
  const report = JSON.parse(await readFile(jsonPath, "utf8"));
  const ipReport = report.rules.find(
    (item) => item.rule_id === "ip_ownership",
  );
  assert(report.audit.length === 1, "JSON 报告审计为 1 条");
  assert(ipReport?.final_status === "pass", "JSON 报告反映人工结论");
  assert(
    dialogs.length === 2 &&
      dialogs.every((message) => message.includes("仍有 1 条需人工确认")),
    "导出前提示待确认项",
  );

  if (screenshotPath) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`截图已保存：${screenshotPath}`);
  }

  await page.getByRole("button", { name: "修改文本 / 重新审查" }).click();
  assert(await page.locator("textarea").isVisible(), "可返回修改文本");

  console.log("E2E smoke passed");
} finally {
  await browser.close();
}
