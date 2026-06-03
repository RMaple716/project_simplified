/**
 * 工作流程日志工具
 * 用于追踪从需求提交到行程展示的完整流程
 */

interface WorkflowStep {
  step: string;
  timestamp: number;
  data?: any;
}

class WorkflowLogger {
  private steps: WorkflowStep[] = [];
  private workflowId: string;

  constructor() {
    this.workflowId = `workflow-${Date.now()}`;
  }

  /**
   * 开始新的工作流程
   */
  startWorkflow(type: string, data?: any) {
    this.steps = [];
    this.workflowId = `workflow-${Date.now()}`;

    console.group(`%c🚀 工作流程开始 [${this.workflowId}]`, 'color: #1890ff; font-weight: bold; font-size: 14px;');
    console.log('%c类型:', 'color: #1890ff;', type);
    console.log('%c初始数据:', 'color: #1890ff;', data);
    console.groupEnd();

    this.logStep('start', { type, data });
  }

  /**
   * 记录步骤
   */
  logStep(step: string, data?: any) {
    const stepData: WorkflowStep = {
      step,
      timestamp: Date.now(),
      data
    };

    this.steps.push(stepData);

    console.group(`%c📝 步骤: ${step}`, 'color: #52c41a; font-weight: bold;');
    console.log('%c时间:', 'color: #52c41a;', new Date(stepData.timestamp).toLocaleTimeString());
    console.log('%c数据:', 'color: #52c41a;', data);
    console.groupEnd();
  }

  /**
   * 记录错误
   */
  logError(step: string, error: any) {
    console.group(`%c❌ 错误: ${step}`, 'color: #ff4d4f; font-weight: bold;');
    console.error(error);
    console.groupEnd();

    this.logStep(`error_${step}`, { error: error.message || error });
  }

  /**
   * 记录API调用
   */
  logApiCall(method: string, url: string, data?: any) {
    console.group(`%c🌐 API调用`, 'color: #1890ff; font-weight: bold;');
    console.log('%c方法:', 'color: #1890ff;', method);
    console.log('%cURL:', 'color: #1890ff;', url);
    console.log('%c请求数据:', 'color: #1890ff;', data);
    console.groupEnd();

    this.logStep(`api_${method}_${url}`, { method, url, data });
  }

  /**
   * 记录API响应
   */
  logApiResponse(method: string, url: string, response: any) {
    console.group(`%c📥 API响应`, 'color: #52c41a; font-weight: bold;');
    console.log('%c方法:', 'color: #52c41a;', method);
    console.log('%cURL:', 'color: #52c41a;', url);
    console.log('%c状态码:', 'color: #52c41a;', response?.code);
    console.log('%c响应数据:', 'color: #52c41a;', response?.data);
    console.groupEnd();

    this.logStep(`api_response_${method}_${url}`, { 
      code: response?.code,
      data: response?.data 
    });
  }

  /**
   * 记录路由跳转
   */
  logRoute(from: string, to: string, params?: any) {
    console.group(`%c🔄 路由跳转`, 'color: #722ed1; font-weight: bold;');
    console.log('%c从:', 'color: #722ed1;', from);
    console.log('%c到:', 'color: #722ed1;', to);
    console.log('%c参数:', 'color: #722ed1;', params);
    console.groupEnd();

    this.logStep(`route_${from}_to_${to}`, { from, to, params });
  }

  /**
   * 记录数据转换
   */
  logDataTransform(fromType: string, toType: string, data: any) {
    console.group(`%c📊 数据转换`, 'color: #faad14; font-weight: bold;');
    console.log('%c从:', 'color: #faad14;', fromType);
    console.log('%c到:', 'color: #faad14;', toType);
    console.log('%c原始数据:', 'color: #faad14;', data);
    console.groupEnd();

    this.logStep(`transform_${fromType}_to_${toType}`, { fromType, toType, data });
  }

  /**
   * 记录关键数据
   */
  logKeyData(key: string, value: any) {
    console.group(`%c🔑 关键数据: ${key}`, 'color: #eb2f96; font-weight: bold;');
    console.log('%c值:', 'color: #eb2f96;', value);
    console.log('%c类型:', 'color: #eb2f96;', typeof value);
    console.log('%c长度:', 'color: #eb2f96;', value?.length || 'N/A');
    console.groupEnd();

    this.logStep(`key_data_${key}`, { key, value, type: typeof value });
  }

  /**
   * 完成工作流程
   */
  endWorkflow(status: 'success' | 'failed', message?: string) {
    const duration = this.steps.length > 0 
      ? this.steps[this.steps.length - 1].timestamp - this.steps[0].timestamp
      : 0;

    console.group(`%c✅ 工作流程完成 [${this.workflowId}]`, 'color: #52c41a; font-weight: bold; font-size: 14px;');
    console.log('%c状态:', 'color: #52c41a;', status);
    console.log('%c消息:', 'color: #52c41a;', message);
    console.log('%c总耗时:', 'color: #52c41a;', `${duration}ms`);
    console.log('%c步骤数:', 'color: #52c41a;', this.steps.length);
    console.groupEnd();

    this.logStep('end', { status, message, duration });

    // 打印完整流程摘要
    this.printSummary();
  }

  /**
   * 打印流程摘要
   */
  private printSummary() {
    console.group(`%c📋 流程摘要 [${this.workflowId}]`, 'color: #722ed1; font-weight: bold;');

    this.steps.forEach((step, index) => {
      const icon = step.step.startsWith('error') ? '❌' : '✅';
      const color = step.step.startsWith('error') ? '#ff4d4f' : '#52c41a';
      console.log(
        `%c${index + 1}. ${icon} ${step.step}`, 
        `color: ${color};`
      );
    });

    console.groupEnd();
  }

  /**
   * 获取所有步骤
   */
  getSteps(): WorkflowStep[] {
    return this.steps;
  }

  /**
   * 获取工作流程ID
   */
  getWorkflowId(): string {
    return this.workflowId;
  }
}

// 导出单例
export const workflowLogger = new WorkflowLogger();
