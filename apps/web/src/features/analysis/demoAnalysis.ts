/** Synthetic versioned fixture; never represents uploaded customer feedback. */
export const demoAnalysis = {
  version: 'demo-v1', validFeedback: 12,
  summary: '12 条合成反馈中，物流体验被提及最多，其次为退款进度和产品使用。主题只用于定位待核查线索，请结合原文判断。',
  topics: [
    { id: 'delivery', title: '物流体验', count: 6, summary: '配送等待与物流更新是主要关注点。', evidence: '合成样本 DEMO-001：包裹等待了三天，物流信息一直没有更新。' },
    { id: 'refund', title: '退款进度', count: 4, summary: '反馈关注退款处理时间和状态透明度。', evidence: '合成样本 DEMO-002：申请退款后，希望能看到预计到账时间。' },
    { id: 'product', title: '产品使用', count: 2, summary: '使用引导与功能说明仍有改善空间。', evidence: '合成样本 DEMO-003：第一次使用时没有找到操作说明。' },
  ],
} as const
