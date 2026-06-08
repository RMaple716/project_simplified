/**
 * 前端日志工具
 * 提供带颜色和标签的日志输出，便于调试和问题排查
 */

export enum LogLevel {
  INFO = 'info',
  SUCCESS = 'success',
  WARN = 'warn',
  ERROR = 'error'
}

export interface LogConfig {
  tag: string;
  message: string;
  data?: any;
}

class Logger {
  private isDevelopment: boolean;

  constructor() {
    // 安全检测 NODE_ENV（Vite 会编译时替换，TypeScript 环境可能无 process）
    this.isDevelopment = 
      typeof (import.meta as any)?.env?.DEV !== 'undefined' 
        ? (import.meta as any).env.DEV === true
        : true;
  }

  private formatLog(level: LogLevel, tag: string, message: string): string {
    const timestamp = new Date().toISOString();
    return `[${timestamp}] [${level.toUpperCase()}] [${tag}] ${message}`;
  }

  private getStyle(level: LogLevel): string {
    switch (level) {
      case LogLevel.INFO:
        return 'color: #1890ff; font-weight: bold;';
      case LogLevel.SUCCESS:
        return 'color: #52c41a; font-weight: bold;';
      case LogLevel.WARN:
        return 'color: #faad14; font-weight: bold;';
      case LogLevel.ERROR:
        return 'color: #ff4d4f; font-weight: bold;';
      default:
        return 'color: #000; font-weight: bold;';
    }
  }

  private log(level: LogLevel, config: LogConfig) {
    if (!this.isDevelopment) return;

    const { tag, message, data } = config;
    const formattedMessage = this.formatLog(level, tag, message);
    const style = this.getStyle(level);

    if (data) {
      console.log(`%c${formattedMessage}`, style, data);
    } else {
      console.log(`%c${formattedMessage}`, style);
    }
  }

  info(tag: string, message: string, data?: any) {
    this.log(LogLevel.INFO, { tag, message, data });
  }

  success(tag: string, message: string, data?: any) {
    this.log(LogLevel.SUCCESS, { tag, message, data });
  }

  warn(tag: string, message: string, data?: any) {
    this.log(LogLevel.WARN, { tag, message, data });
  }

  error(tag: string, message: string, error?: any) {
    this.log(LogLevel.ERROR, { tag, message, data: error });
  }

  // 专门用于数据流的日志
  dataFlow(tag: string, step: string, data: any) {
    if (!this.isDevelopment) return;

    console.group(`%c📊 数据流 - ${tag} - ${step}`, 'color: #722ed1; font-weight: bold;');
    console.log('数据类型:', typeof data);
    console.log('数据内容:', data);
    if (Array.isArray(data)) {
      console.log('数组长度:', data.length);
    } else if (typeof data === 'object' && data !== null) {
      console.log('对象键:', Object.keys(data));
    }
    console.groupEnd();
  }

  // 专门用于API调用的日志
  apiCall(tag: string, method: string, url: string, data?: any) {
    if (!this.isDevelopment) return;

    console.group(`%c🌐 API调用 - ${tag}`, 'color: #13c2c2; font-weight: bold;');
    console.log('方法:', method);
    console.log('URL:', url);
    if (data) {
      console.log('请求数据:', data);
    }
    console.groupEnd();
  }

  apiResponse(tag: string, status: number, data?: any) {
    if (!this.isDevelopment) return;

    const isSuccess = status >= 200 && status < 300;
    const style = isSuccess ? 'color: #52c41a; font-weight: bold;' : 'color: #ff4d4f; font-weight: bold;';

    console.group(`%c📥 API响应 - ${tag}`, style);
    console.log('状态码:', status);
    if (data) {
      console.log('响应数据:', data);
    }
    console.groupEnd();
  }

  // 专门用于组件生命周期的日志
  componentLifecycle(componentName: string, phase: string, props?: any) {
    if (!this.isDevelopment) return;

    const styles = {
      mount: 'color: #52c41a; font-weight: bold;',
      update: 'color: #1890ff; font-weight: bold;',
      unmount: 'color: #ff4d4f; font-weight: bold;'
    };

    const style = styles[phase as keyof typeof styles] || 'color: #000; font-weight: bold;';

    console.group(`%c🔄 组件生命周期 - ${componentName}`, style);
    console.log('阶段:', phase);
    if (props) {
      console.log('Props:', props);
    }
    console.groupEnd();
  }
}

export const logger = new Logger();
