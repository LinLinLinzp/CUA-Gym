import { defineConfig } from 'vite'
import { stateApi } from '../../templates/state-api.js'
import { createInitialData } from './src/data/seed.js'

export default defineConfig({ plugins: [stateApi(createInitialData)] })
