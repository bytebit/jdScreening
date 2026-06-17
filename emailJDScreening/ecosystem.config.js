// PM2 生态系统配置文件
// AI 简历自动筛选系统
//
// 使用方法:
//   cd 项目目录 && pm2 start ecosystem.config.js
//   pm2 stop resume-filter
//   pm2 restart resume-filter
//   pm2 logs resume-filter
//
// 安装 PM2:
//   npm install -g pm2

module.exports = {
  apps: [{
    name: 'resume-filter',
    script: 'main.py',
    interpreter: './venv/bin/python3',

    // 守护模式：每 5 分钟执行一轮
    args: '--daemon --interval 5',

    // 日志配置
    error_file: './logs/pm2_error.log',
    out_file: './logs/pm2_out.log',
    log_file: './logs/pm2_combined.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss',
    merge_logs: true,

    // 进程管理
    instances: 1,
    exec_mode: 'fork',
    autorestart: true,
    max_restarts: 10,
    restart_delay: 10000,
    max_memory_restart: '500M',

    // 优雅关闭
    kill_timeout: 30000,

    // 环境变量
    env: {
      NODE_ENV: 'production',
    },
  }]
};
