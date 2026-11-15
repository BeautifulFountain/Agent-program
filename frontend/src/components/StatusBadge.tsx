const labels: Record<string, string> = { queued: '排队中', running: '运行中', waiting_approval: '等待人工确认', completed: '已完成', failed: '失败', cancelled: '已取消', needs_review: '需人工审核', reworking: '返工中', active: '启用', disabled: '停用' }

export default function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-${status}`}><span/>{labels[status] ?? status}</span>
}

