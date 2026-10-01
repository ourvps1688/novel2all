const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");

const { createApp } = require("../dist/app.js");
const { DirectorAttentionService } = require("../dist/services/novel/director/DirectorAttentionService.js");

function listen(server) {
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve(address.port);
    });
  });
}

function request(port, path) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: "127.0.0.1", port, path, method: "GET" }, (res) => {
      let body = "";
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        resolve({ status: res.statusCode, body: body ? JSON.parse(body) : null });
      });
    });
    req.on("error", reject);
    req.end();
  });
}

test("director-attention routes expose single + aggregate endpoints", async () => {
  const originals = {
    getAttention: DirectorAttentionService.prototype.getAttention,
    listAttentions: DirectorAttentionService.prototype.listAttentions,
  };
  let server;
  try {
    DirectorAttentionService.prototype.getAttention = async function getAttentionMock(novelId) {
      if (novelId === "missing") return null;
      return {
        novelId,
        novelTitle: "My Book",
        level: "needs_recovery",
        headline: "Recovery needed",
        detail: "stuck",
        requiresUserAction: true,
        primaryAction: { type: "retry", target: { novelId } },
        fallbackActions: [],
        updatedAt: "2026-01-01T00:00:00.000Z",
      };
    };
    DirectorAttentionService.prototype.listAttentions = async function listAttentionsMock() {
      return [
        {
          novelId: "novel_2",
          novelTitle: "Other Book",
          level: "waiting_approval",
          headline: "Approval needed",
          detail: null,
          requiresUserAction: true,
          primaryAction: { type: "confirm_candidate", target: { novelId: "novel_2" } },
          fallbackActions: [],
          updatedAt: "2026-01-01T00:00:00.000Z",
        },
      ];
    };

    const app = createApp();
    server = http.createServer(app);
    const port = await listen(server);

    const single = await request(port, "/api/director-attentions/novel_1");
    assert.equal(single.status, 200);
    assert.equal(single.body.data.attention.level, "needs_recovery");
    assert.ok(single.body.data.attention.primaryAction);

    const missing = await request(port, "/api/director-attentions/missing");
    assert.equal(missing.status, 404);

    const list = await request(port, "/api/director-attentions");
    assert.equal(list.status, 200);
    assert.equal(list.body.data.attentions.length, 1);
    assert.equal(list.body.data.attentions[0].level, "waiting_approval");
  } finally {
    DirectorAttentionService.prototype.getAttention = originals.getAttention;
    DirectorAttentionService.prototype.listAttentions = originals.listAttentions;
    if (server) {
      await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
    }
  }
});
