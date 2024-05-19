import { useState } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'

import { testAPI } from './utils/api';

function App() {
  const [count, setCount] = useState(0)
  const [value1, setValue1] = useState(0);
  const [value2, setValue2] = useState(0);
  const [result, setResult] = useState<number>();

  async function getResult() {
    setResult(await testAPI(value1, value2));
  }

  return (
    <>
      <div>
        <a href="https://vitejs.dev" target="_blank">
          <img src={viteLogo} className="logo" alt="Vite logo" />
        </a>
        <a href="https://react.dev" target="_blank">
          <img src={reactLogo} className="logo react" alt="React logo" />
        </a>
      </div>
      <h1>Vite + React</h1>
      <div className="card">
        <button onClick={() => setCount((count) => count + 1)}>
          count is {count}
        </button>
        <p>
          Edit <code>src/App.tsx</code> and save to test HMR
        </p>
      </div>
      <p className="read-the-docs">
        Click on the Vite and React logos to learn more
      </p>

      <input type='number' value={value1} onChange={event => setValue1(parseInt(event.currentTarget.value))}/>
      +
      <input type='number' value={value2} onChange={event => setValue2(parseInt(event.currentTarget.value))}/>
      =
      {result ?? '?'}
      <br/>
      <button onClick={getResult}>Calculate</button>
    </>
  )
}

export default App
