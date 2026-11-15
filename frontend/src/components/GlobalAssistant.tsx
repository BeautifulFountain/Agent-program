import { Bot, GripHorizontal, LoaderCircle, Maximize2, MessageCircle, Send, Sparkles, X } from 'lucide-react'
import { FormEvent, PointerEvent as ReactPointerEvent, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'

type Message={role:'user'|'assistant';content:string}
type ChatResult={reply:string;tokens:number;mode:string}
type Point={x:number;y:number}

const welcome:Message={role:'assistant',content:'你好，我是你的 AI 智能伙伴。你可以和我日常聊天、学习讨论、润色写作或咨询代码；涉及 AgentFlow 时，我也能结合当前任务、Agent 和工作流状态提供帮助。'}
const quickPrompts=['当前有哪些任务？','帮我润色一段文字','和我聊聊人工智能']

export default function GlobalAssistant(){
  const location=useLocation();const[open,setOpen]=useState(false);const[messages,setMessages]=useState<Message[]>([welcome]);const[input,setInput]=useState('');const[loading,setLoading]=useState(false);const[error,setError]=useState('');const listRef=useRef<HTMLDivElement>(null);const draggedRef=useRef(false)
  const[position,setPosition]=useState<Point>(()=>{try{const saved=localStorage.getItem('agentflow-assistant-position');if(saved)return JSON.parse(saved)}catch{/* use default */}return{x:Math.max(24,window.innerWidth-86),y:82}})
  useEffect(()=>{listRef.current?.scrollTo({top:listRef.current.scrollHeight,behavior:'smooth'})},[messages,loading])
  useEffect(()=>{const clamp=()=>setPosition(current=>({x:Math.min(Math.max(16,current.x),window.innerWidth-70),y:Math.min(Math.max(72,current.y),window.innerHeight-70)}));window.addEventListener('resize',clamp);return()=>window.removeEventListener('resize',clamp)},[])
  const startDrag=(event:ReactPointerEvent<HTMLButtonElement>)=>{event.preventDefault();draggedRef.current=false;const origin={x:event.clientX,y:event.clientY};const start=position;event.currentTarget.setPointerCapture(event.pointerId);const move=(pointer:PointerEvent)=>{if(Math.abs(pointer.clientX-origin.x)+Math.abs(pointer.clientY-origin.y)>5)draggedRef.current=true;setPosition({x:Math.min(Math.max(16,start.x+pointer.clientX-origin.x),window.innerWidth-70),y:Math.min(Math.max(72,start.y+pointer.clientY-origin.y),window.innerHeight-70)})};const up=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);setPosition(current=>{localStorage.setItem('agentflow-assistant-position',JSON.stringify(current));return current})};window.addEventListener('pointermove',move);window.addEventListener('pointerup',up)}
  const send=async(text=input)=>{const content=text.trim();if(!content||loading)return;const next=[...messages,{role:'user' as const,content}];setMessages(next);setInput('');setLoading(true);setError('');try{const result=await api<ChatResult>('/api/assistant/chat',{method:'POST',body:JSON.stringify({message:content,history:messages.slice(-8),page:location.pathname})});setMessages([...next,{role:'assistant',content:result.reply}])}catch(reason){setError(reason instanceof Error?reason.message:'智能伙伴暂时不可用')}finally{setLoading(false)}}
  const submit=(event:FormEvent)=>{event.preventDefault();void send()}
  const opensUp=position.y>window.innerHeight-620
  return <div className={`global-assistant ${open?'is-open':''} ${opensUp?'opens-up':''}`} style={{transform:`translate3d(${position.x}px,${position.y}px,0)`}}>
    {open&&<section className="assistant-panel" role="dialog" aria-label="AI 智能伙伴"><header><div className="assistant-identity"><span><Sparkles size={17}/></span><div><strong>AI 智能伙伴</strong><small>日常问答 · 学习创作 · 全局协作</small></div></div><button className="assistant-close" aria-label="关闭智能伙伴" onClick={()=>setOpen(false)}><X size={18}/></button></header><div className="assistant-drag-hint"><GripHorizontal size={15}/><span>拖动右侧悬浮按钮可改变位置</span></div><div className="assistant-messages" ref={listRef} aria-live="polite">{messages.map((message,index)=><article key={index} className={`assistant-message ${message.role}`}><span>{message.role==='assistant'?<Bot size={15}/>:null}</span><p>{message.content}</p></article>)}{loading&&<div className="assistant-thinking"><LoaderCircle size={15}/>正在思考…</div>}{error&&<p className="assistant-error" role="alert">{error}</p>}</div>{messages.length===1&&<div className="assistant-quick">{quickPrompts.map(prompt=><button key={prompt} onClick={()=>void send(prompt)}>{prompt}</button>)}</div>}<form className="assistant-input" onSubmit={submit}><label className="sr-only" htmlFor="global-assistant-input">向智能伙伴提问</label><textarea id="global-assistant-input" rows={2} value={input} onChange={event=>setInput(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();void send()}}} placeholder="和我聊聊，或询问任务与 Agent…"/><button aria-label="发送问题" disabled={!input.trim()||loading}><Send size={17}/></button></form><footer>由 DeepSeek 驱动 · 平台问题会结合实时摘要</footer></section>}
    <button className="assistant-orb" aria-label={open?'拖动智能伙伴位置':'打开 AgentFlow 智能伙伴'} title={open?'拖动改变位置':'打开智能伙伴'} onPointerDown={startDrag} onClick={()=>{if(draggedRef.current){draggedRef.current=false;return}setOpen(value=>!value)}}><MessageCircle size={23}/><span className="assistant-orb-pulse"/><Maximize2 className="assistant-drag-mark" size={11}/></button>
  </div>
}
