import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as SelectPrimitive from '@radix-ui/react-select'
import { Check, ChevronDown, X } from 'lucide-react'
import { cva, type VariantProps } from 'class-variance-authority'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)) }

const buttonVariants = cva('inline-flex shrink-0 items-center justify-center gap-2 rounded-lg text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:pointer-events-none disabled:opacity-40', {
  variants: {
    variant: { default: 'bg-ink text-white hover:bg-[#344152]', secondary: 'bg-white text-ink border border-line hover:bg-[#f2f4f7]', ghost: 'text-muted hover:bg-[#edf0f4] hover:text-ink', danger: 'text-[#a13a37] hover:bg-[#fff2f0]' },
    size: { default: 'h-9 px-3.5', sm: 'h-8 px-3', icon: 'h-9 w-9 p-0' }
  },
  defaultVariants: { variant: 'default', size: 'default' }
})
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button({className,variant,size,type='button',...props},ref){return <button type={type} className={cn(buttonVariants({variant,size}),className)} ref={ref} {...props}/>})

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input({className,...props},ref){return <input ref={ref} className={cn('h-9 w-full rounded-lg border border-line bg-white px-3 text-sm text-ink placeholder:text-[#97a0ac] focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand',className)} {...props}/>})

export function Card({className,children,...props}:React.HTMLAttributes<HTMLDivElement>) {return <div className={cn('rounded-xl border border-line bg-white',className)} {...props}>{children}</div>}
export function Badge({children, tone='neutral'}: {children:React.ReactNode,tone?:'neutral'|'success'|'warning'|'danger'}) {return <span className={cn('inline-flex items-center rounded-md px-2 py-1 text-xs font-medium',tone==='neutral'&&'bg-[#eef1f5] text-[#536171]',tone==='success'&&'bg-[#e8f5ef] text-[#276348]',tone==='warning'&&'bg-[#fff2dd] text-[#805c1e]',tone==='danger'&&'bg-[#fce9e8] text-[#8e3c37]')}>{children}</span>}

export const Dialog = DialogPrimitive.Root
export const DialogTitle = DialogPrimitive.Title
export const DialogDescription = DialogPrimitive.Description
export function DialogContent({children}: {children:React.ReactNode}) {return <DialogPrimitive.Portal><DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-ink/30"/><DialogPrimitive.Content className="fixed inset-y-0 right-0 z-50 flex h-full w-full max-w-xl flex-col overflow-y-auto bg-white p-7 shadow-2xl focus:outline-none"><DialogPrimitive.Close aria-label="Close details" className="absolute right-5 top-5 rounded-lg p-2 text-muted hover:bg-canvas focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"><X size={18}/></DialogPrimitive.Close>{children}</DialogPrimitive.Content></DialogPrimitive.Portal>}

export function Select({value,onChange,options,label}: {value:string,onChange:(v:string)=>void,options:{value:string,label:string}[],label:string}){
return <SelectPrimitive.Root value={value} onValueChange={onChange}><SelectPrimitive.Trigger aria-label={label} className="flex h-9 min-w-[150px] items-center justify-between gap-3 rounded-lg border border-line bg-white px-3 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-brand/25"><SelectPrimitive.Value/><SelectPrimitive.Icon><ChevronDown size={14}/></SelectPrimitive.Icon></SelectPrimitive.Trigger><SelectPrimitive.Portal><SelectPrimitive.Content position="popper" sideOffset={4} className="z-[80] min-w-[170px] rounded-lg border border-line bg-white p-1 shadow-lg"><SelectPrimitive.Viewport>{options.map(o=><SelectPrimitive.Item key={o.value} value={o.value} className="relative cursor-pointer select-none rounded-md py-2 pl-8 pr-3 text-sm text-ink outline-none data-[highlighted]:bg-soft"><SelectPrimitive.ItemIndicator className="absolute left-2 top-2.5"><Check size={14}/></SelectPrimitive.ItemIndicator><SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText></SelectPrimitive.Item>)}</SelectPrimitive.Viewport></SelectPrimitive.Content></SelectPrimitive.Portal></SelectPrimitive.Root>}