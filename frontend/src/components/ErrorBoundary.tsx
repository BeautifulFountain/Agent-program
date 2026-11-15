import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = { children: ReactNode }
type State = { hasError: boolean; message: string }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message || '页面数据格式异常' }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('AgentFlow page error', error, info)
  }

  render() {
    if (this.state.hasError) {
      return <main className="fatal-error" role="alert">
        <AlertTriangle size={30}/>
        <h1>页面暂时无法显示</h1>
        <p>{this.state.message}</p>
        <button className="button primary" onClick={() => window.location.reload()}>
          <RefreshCw size={17}/>重新加载
        </button>
      </main>
    }
    return this.props.children
  }
}

