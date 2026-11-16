const labels: Record<string, string> = { queued: '排队中', running: '执行中', waiting_approval: '等待需求确认', waiting_final_acceptance: '已完成', completed: '已完成', failed: '失败', rejected: '已驳回', cancelled: '已取消', needs_review: '已完成', reworking: '返工中', active: '启用', disabled: '停用' }

export default function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-${status}`}><span/>{labels[status] ?? status}</span>
}

