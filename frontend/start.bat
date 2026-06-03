@echo off
echo ========================================
echo   启动旅游行程规划系统
echo ========================================
echo.

echo 正在启动后端服务...
start "后端服务" cmd /k "cd .. && python src\index.py"

echo 等待后端服务启动（5秒）...
timeout /t 5 /nobreak >nul

echo.
echo 正在启动前端开发服务器...
start "前端服务" cmd /k "npm run dev"

echo.
echo ========================================
echo   ✅ 系统启动中...
echo ========================================
echo.
echo 后端服务: http://127.0.0.1:9091
echo 前端应用: http://localhost:3000
echo API文档:  http://127.0.0.1:9091/docs
echo.
echo 提示: 请等待几秒钟后在浏览器中打开前端应用
echo.

pause
