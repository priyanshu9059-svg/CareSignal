import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',workers:1,use:{baseURL:'http://127.0.0.1:3000',channel:process.env.PLAYWRIGHT_CHANNEL||undefined,headless:true,screenshot:'only-on-failure',permissions:['microphone'],launchOptions:{args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']}},timeout:90000,reporter:'list'});
