/**
 * 仙尊名人堂 — 飞升碑林
 *
 * Phase 3C：REST API 获取排行榜 + Canvas 2D 沙雕战报图分享。
 * 美学方向：碑林石韵 — 古石碑铭刻，金/银/铜光晕。
 */

import { BASE_URL } from '../../utils/config';

interface HallRecord {
  player_name: string;
  ascension_title: string;
  total_heaven_points: number;
  ascended_at: string;
}

/* 排名对应的中文数字 */
const RANK_LABELS: Record<number, string> = {
  1: '壹', 2: '贰', 3: '叁', 4: '肆', 5: '伍',
  6: '陆', 7: '柒', 8: '捌', 9: '玖', 10: '拾',
};

function rankLabel(rank: number): string {
  return RANK_LABELS[rank] || String(rank);
}

Page({
  data: {
    records: [] as HallRecord[],
    total: 0,
    loading: true,
    empty: false,
    /** 战报图绘制中 */
    drawing: false,
    /** 当前生成战报的记录索引 */
    battleIndex: -1,
  },

  onLoad() {
    this._fetchHall();
  },

  onShow() {
    // 从其他 tab 切回时刷新
    if (!this.data.loading) {
      this._fetchHall();
    }
  },

  onPullDownRefresh() {
    this._fetchHall().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  /* ── 数据获取 ── */

  async _fetchHall() {
    this.setData({ loading: true });

    try {
      const res = await this._request<{ records: HallRecord[]; total: number }>(
        `${BASE_URL}/api/hall/top?limit=50`,
        'GET',
      );
      const records = res.records || [];
      this.setData({
        records,
        total: res.total || records.length,
        loading: false,
        empty: records.length === 0,
      });
    } catch {
      this.setData({ loading: false, empty: this.data.records.length === 0 });
    }
  },

  _request<T>(url: string, method: 'GET' | 'POST', data?: unknown): Promise<T> {
    return new Promise((resolve, reject) => {
      wx.request({
        url,
        method,
        header: method === 'POST' ? { 'content-type': 'application/json' } : {},
        data: data as Record<string, unknown>,
        success: (res) => {
          if (res.statusCode === 200) {
            resolve(res.data as T);
          } else {
            reject(res);
          }
        },
        fail: reject,
      });
    });
  },

  /* ── 点击记录 → 生成战报图 ── */

  onTapRecord(e: WechatMiniprogram.TouchEvent) {
    const index = Number(e.currentTarget.dataset.index);
    const record = this.data.records[index];
    if (!record || this.data.drawing) return;

    const rank = index + 1;
    this.setData({ drawing: true, battleIndex: index });
    this._drawBattleReport(record, rank);
  },

  async _drawBattleReport(record: HallRecord, rank: number) {
    try {
      const tempPath = await this._renderCanvas(record, rank);
      this.setData({ drawing: false, battleIndex: -1 });

      // 弹出分享菜单
      wx.showShareImageMenu({
        path: tempPath,
        fail: () => {
          // 降级：预览图片
          wx.previewImage({
            urls: [tempPath],
            current: tempPath,
          });
        },
      });
    } catch (err) {
      console.error('[Hall] 战报图生成失败:', err);
      this.setData({ drawing: false, battleIndex: -1 });
      wx.showToast({ title: '战报图生成失败', icon: 'none', duration: 1500 });
    }
  },

  /* ── Canvas 2D 绘制 ── */

  _renderCanvas(record: HallRecord, rank: number): Promise<string> {
    return new Promise((resolve, reject) => {
      const query = wx.createSelectorQuery();
      query
        .select('#battleReportCanvas')
        .fields({ node: true, size: true })
        .exec((res) => {
          if (!res || !res[0] || !res[0].node) {
            reject(new Error('Canvas 节点未找到'));
            return;
          }

          const canvas = res[0].node as WechatMiniprogram.Canvas;
          const ctx = canvas.getContext('2d') as WechatMiniprogram.CanvasRenderingContext2D;

          const w = 600;
          const h = 800;
          const dpr = wx.getSystemInfoSync().pixelRatio;
          canvas.width = w * dpr;
          canvas.height = h * dpr;
          ctx.scale(dpr, dpr);

          // ── 水墨背景 ──
          // 底色
          const bgGrad = ctx.createLinearGradient(0, 0, 0, h);
          bgGrad.addColorStop(0, '#080814');
          bgGrad.addColorStop(0.5, '#0c101c');
          bgGrad.addColorStop(1, '#111627');
          ctx.fillStyle = bgGrad;
          ctx.fillRect(0, 0, w, h);

          // 墨渍晕染效果
          ctx.save();
          for (let i = 0; i < 5; i++) {
            const cx = 80 + Math.random() * 440;
            const cy = 100 + Math.random() * 600;
            const r = 40 + Math.random() * 80;
            const spotGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
            spotGrad.addColorStop(0, 'rgba(28, 36, 60, 0.25)');
            spotGrad.addColorStop(1, 'rgba(28, 36, 60, 0)');
            ctx.fillStyle = spotGrad;
            ctx.fillRect(cx - r, cy - r, r * 2, r * 2);
          }
          ctx.restore();

          // 竖线纹理（模拟碑石纹路）
          ctx.save();
          ctx.strokeStyle = 'rgba(42, 48, 68, 0.12)';
          ctx.lineWidth = 0.5;
          for (let x = 30; x < w; x += 18) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x + (Math.random() - 0.5) * 8, h);
            ctx.stroke();
          }
          ctx.restore();

          // ── 顶部装饰：卷云纹 ──
          ctx.save();
          ctx.strokeStyle = 'rgba(200, 160, 80, 0.25)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(60, 70);
          ctx.quadraticCurveTo(150, 50, 200, 70);
          ctx.quadraticCurveTo(250, 50, 300, 70);
          ctx.quadraticCurveTo(350, 50, 400, 70);
          ctx.quadraticCurveTo(450, 50, 540, 70);
          ctx.stroke();
          ctx.restore();

          // ── 标题 ──
          ctx.save();
          ctx.fillStyle = '#c9a050';
          ctx.font = 'bold 30px "PingFang SC", "Microsoft YaHei", serif';
          ctx.textAlign = 'center';
          ctx.fillText('仙 尊 名 人 堂', w / 2, 120);

          ctx.fillStyle = '#7a8090';
          ctx.font = '16px "PingFang SC", "Microsoft YaHei", serif';
          ctx.fillText('—— 飞升碑林 · 不朽铭文 ——', w / 2, 150);
          ctx.restore();

          // ── 分隔线 ──
          ctx.save();
          const sepGrad = ctx.createLinearGradient(80, 0, w - 80, 0);
          sepGrad.addColorStop(0, 'rgba(200, 160, 80, 0.08)');
          sepGrad.addColorStop(0.5, 'rgba(200, 160, 80, 0.35)');
          sepGrad.addColorStop(1, 'rgba(200, 160, 80, 0.08)');
          ctx.strokeStyle = sepGrad;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(80, 170);
          ctx.lineTo(w - 80, 170);
          ctx.stroke();
          ctx.restore();

          // ── 排名徽章 ──
          const rankColors: Record<number, { bg: string; border: string; text: string }> = {
            1: { bg: 'rgba(200, 160, 80, 0.12)', border: '#c9a050', text: '#e8c45a' },
            2: { bg: 'rgba(160, 170, 190, 0.10)', border: '#8a8fa0', text: '#b8c0d0' },
            3: { bg: 'rgba(180, 140, 100, 0.10)', border: '#9a7a5a', text: '#c8a870' },
          };
          const rc = rankColors[rank] || { bg: 'rgba(120, 130, 150, 0.06)', border: '#5a6070', text: '#8a90a0' };

          // 排名圆徽
          ctx.save();
          ctx.fillStyle = rc.bg;
          ctx.strokeStyle = rc.border;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(w / 2, 230, 40, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();

          ctx.fillStyle = rc.text;
          ctx.font = 'bold 36px "PingFang SC", "Microsoft YaHei", serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          const rankText = rank <= 10 ? rankLabel(rank) : `#${rank}`;
          ctx.fillText(rankText, w / 2, 230);
          ctx.restore();

          // ── 修士道号 ──
          ctx.save();
          ctx.fillStyle = '#e8dbc0';
          ctx.font = 'bold 28px "PingFang SC", "Microsoft YaHei", serif';
          ctx.textAlign = 'center';
          ctx.fillText(record.player_name, w / 2, 300);
          ctx.restore();

          // ── 飞升封号 ──
          ctx.save();
          ctx.fillStyle = '#c9a050';
          ctx.font = '22px "PingFang SC", "Microsoft YaHei", serif';
          ctx.textAlign = 'center';
          ctx.fillText(`「${record.ascension_title}」`, w / 2, 340);
          ctx.restore();

          // ── 信息横线 ──
          ctx.save();
          ctx.strokeStyle = 'rgba(200, 160, 80, 0.2)';
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(150, 370);
          ctx.lineTo(w - 150, 370);
          ctx.stroke();
          ctx.restore();

          // ── 详细属性 ──
          const lines = [
            { label: '天 道 点', value: record.total_heaven_points.toLocaleString() },
            { label: '飞升排名', value: `第 ${rank} 位` },
            { label: '飞升时日', value: this._formatDate(record.ascended_at) },
          ];

          ctx.save();
          lines.forEach((line, i) => {
            const y = 410 + i * 52;
            ctx.fillStyle = '#7a8090';
            ctx.font = '16px "PingFang SC", "Microsoft YaHei", serif';
            ctx.textAlign = 'left';
            ctx.fillText(line.label, 180, y);

            ctx.fillStyle = '#e8dbc0';
            ctx.font = 'bold 20px "PingFang SC", "Microsoft YaHei", serif';
            ctx.textAlign = 'right';
            ctx.fillText(line.value, w - 180, y);
          });
          ctx.restore();

          // ── 底部装饰 ──
          ctx.save();
          ctx.strokeStyle = 'rgba(200, 160, 80, 0.25)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(60, h - 100);
          ctx.quadraticCurveTo(150, h - 80, 200, h - 100);
          ctx.quadraticCurveTo(250, h - 80, 300, h - 100);
          ctx.quadraticCurveTo(350, h - 80, 400, h - 100);
          ctx.quadraticCurveTo(450, h - 80, 540, h - 100);
          ctx.stroke();
          ctx.restore();

          // 底栏铭文
          ctx.save();
          ctx.fillStyle = '#2a2d3a';
          ctx.font = '14px "PingFang SC", "Microsoft YaHei", serif';
          ctx.textAlign = 'center';
          ctx.fillText('—— 虚无之中 · 因果可易 ——', w / 2, h - 58);
          ctx.fillText('天道不正经 · 仙尊名人堂', w / 2, h - 35);
          ctx.restore();

          // ── 四角封印 ──
          this._drawSealCorners(ctx, w, h);

          // ── 导出图片 ──
          wx.canvasToTempFilePath({
            canvas,
            x: 0,
            y: 0,
            width: w,
            height: h,
            destWidth: w * 2,
            destHeight: h * 2,
            fileType: 'png',
            quality: 1,
            success: (res) => resolve(res.tempFilePath),
            fail: reject,
          });
        });
    });
  },

  _drawSealCorners(ctx: WechatMiniprogram.CanvasRenderingContext2D, w: number, h: number) {
    const corners = [
      [40, 40], [w - 40, 40], [40, h - 40], [w - 40, h - 40],
    ];
    ctx.save();
    ctx.strokeStyle = 'rgba(200, 160, 80, 0.15)';
    ctx.lineWidth = 1;
    corners.forEach(([cx, cy]) => {
      // L 形封印角
      ctx.beginPath();
      ctx.moveTo(cx - 16, cy - 16);
      ctx.lineTo(cx - 16, cy);
      ctx.lineTo(cx, cy);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(cx + 16, cy - 16);
      ctx.lineTo(cx + 16, cy);
      ctx.lineTo(cx, cy);
      ctx.stroke();
    });
    ctx.restore();
  },

  _formatDate(isoStr: string): string {
    if (!isoStr) return '太古纪元';
    try {
      const d = new Date(isoStr);
      const pad = (n: number) => String(n).padStart(2, '0');
      return `${d.getFullYear()}年${pad(d.getMonth() + 1)}月${pad(d.getDate())}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch {
      return isoStr.slice(0, 16);
    }
  },
});
