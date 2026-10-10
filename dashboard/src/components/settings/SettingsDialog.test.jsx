import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import SettingsDialog from './SettingsDialog'
import api from '../../lib/api'
globalThis.IS_REACT_ACT_ENVIRONMENT = true
jest.mock('../../lib/api', () => ({ getSettings:jest.fn(), getProviderModels:jest.fn(), updateSettings:jest.fn() }))
jest.mock('../ui/dialog', () => ({ Dialog:({children})=>children, DialogContent:({children})=><div>{children}</div>, DialogHeader:({children})=><div>{children}</div>, DialogTitle:({children})=><h1>{children}</h1>, DialogDescription:({children})=><p>{children}</p> }))
jest.mock('../ui/scroll-area', () => ({ScrollArea:({children})=><div>{children}</div>}))
const fixture = { app:{llm_provider:'groq', name:'Aiden', user_name:'User', debug:false}, groq:{model:'test-model'}, speech:{}, meta:{} }
let container,root
beforeEach(() => {
  jest.clearAllMocks(); localStorage.clear()
  api.getSettings.mockResolvedValue({settings:fixture})
  api.getProviderModels.mockResolvedValue({models:[], reachable:true})
  api.updateSettings.mockImplementation(settings=>Promise.resolve({settings}))
  container=document.createElement('div'); document.body.appendChild(container); root=createRoot(container)
})
afterEach(()=>{ act(()=>root.unmount()); container.remove() })
const open = async()=>act(async()=>root.render(<SettingsDialog open onOpenChange={()=>{}}/>))
test('appearance applies blue immediately and saves the choice on this device', async()=>{
  await open()
  const blue = [...container.querySelectorAll('button')].find(button=>button.textContent.includes('Aiden blue'))
  act(()=>blue.click())
  expect(document.documentElement.dataset.theme).toBe('aiden-blue')
  expect(localStorage.getItem('aiden-theme')).toBe('aiden-blue')
  expect(api.updateSettings).not.toHaveBeenCalled()
})
test('system edits send the complete settings payload to the existing save API', async()=>{
  await open()
  act(()=>[...container.querySelectorAll('button')].find(button=>button.textContent==='System').click())
  const name = container.querySelector('input[aria-label="name"]')
  act(()=>{
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(name,'My Aiden')
    name.dispatchEvent(new Event('input',{bubbles:true}))
  })
  await act(async()=>container.querySelector('[aria-label="Save settings"]').click())
  expect(api.updateSettings).toHaveBeenCalledWith({...fixture,app:{...fixture.app,name:'My Aiden'}})
})
