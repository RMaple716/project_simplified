import React, { useState } from 'react';
import { Form, Input, InputNumber, DatePicker, Select, Button, Card, message, Row, Col, Divider, Tag, Alert, Space, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { RootState } from '../store';
import { nlpApi, requirementApi } from '../services';
import { parseNaturalDate } from '../utils/helpers';
import type { Dayjs } from 'dayjs';
import { FormOutlined, CompassOutlined, OrderedListOutlined } from '@ant-design/icons';

const { TextArea } = Input;
const { Option } = Select;
const { Text } = Typography;

interface RequirementFormValues {
  natural_language?: string;
  city_name: string;
  attraction?: string;  // ✅ 新增景点字段
  travel_days: number;
  total_budget: number;
  travel_type: string;
  travel_date: Dayjs;
  traveler_count: number;
  preferences: string[];
}

/** 出行类型的中文映射 */
const TRAVEL_TYPE_MAP: Record<string, string> = {
  leisure: '休闲游',
  family: '家庭游',
  adventure: '探险游',
  business: '商务游',
  culture: '文化游',
};

const RequirementForm: React.FC = () => {
  const navigate = useNavigate();
  const user = useSelector((state: RootState) => state.auth.user);
  const currentUserId = user?.user_id || 'anonymous';
  const [form] = Form.useForm<RequirementFormValues>();
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [extractedFields, setExtractedFields] = useState<string[]>([]);
  const [showExtractSummary, setShowExtractSummary] = useState(false);

  /** 高亮自动填充的字段，3秒后消退 */
  const highlightExtractedField = (fieldName: string) => {
    setExtractedFields(prev => [...prev, fieldName]);
    setTimeout(() => {
      setExtractedFields(prev => prev.filter(f => f !== fieldName));
    }, 3000);
  };

  const isFieldHighlighted = (fieldName: string) => {
    return extractedFields.includes(fieldName);
  };

  /** 使用AI智能体从自然语言中提取旅游需求信息 */
  const handleNaturalLanguageSubmit = async () => {
    const text = form.getFieldValue('natural_language');
    if (!text || text.trim().length === 0) {
      message.warning('请输入您的旅游需求');
      return;
    }

    setExtracting(true);
    setShowExtractSummary(false);
    setExtractedFields([]);

    try {
      // 优先使用AI智能体提取（大模型方式）
      const result = await nlpApi.extractByAgent(text);
      const filledFields: string[] = [];

      if (result.city) {
        form.setFieldValue('city_name', result.city);
        filledFields.push('city_name');
        highlightExtractedField('city_name');
      }
      if (result.attraction) {
        form.setFieldValue('attraction', result.attraction);
        filledFields.push('attraction');
        highlightExtractedField('attraction');
      }
      if (result.budget) {
        form.setFieldValue('total_budget', result.budget);
        filledFields.push('total_budget');
        highlightExtractedField('total_budget');
      }
      if (result.people) {
        form.setFieldValue('traveler_count', result.people);
        filledFields.push('traveler_count');
        highlightExtractedField('traveler_count');
      }
      if (result.travel_days) {
        form.setFieldValue('travel_days', result.travel_days);
        filledFields.push('travel_days');
        highlightExtractedField('travel_days');
      }
      if (result.depart_time) {
        const date = parseNaturalDate(result.depart_time);
        if (date) {
          form.setFieldValue('travel_date', date);
          filledFields.push('travel_date');
          highlightExtractedField('travel_date');
        } else {
          console.warn('无法解析日期:', result.depart_time);
        }
      }
      // 大模型特有的偏好提取
      if (result.preferences && result.preferences.length > 0) {
        form.setFieldValue('preferences', result.preferences);
        filledFields.push('preferences');
        highlightExtractedField('preferences');
      }
     // 大模型特有的出行类型提取
      if (result.travel_type && TRAVEL_TYPE_MAP[result.travel_type]) {
        form.setFieldValue('travel_type', result.travel_type);
        filledFields.push('travel_type');
        highlightExtractedField('travel_type');
      }

      if (filledFields.length > 0) {
        setShowExtractSummary(true);
        message.success(`智能提取成功！已自动填充 ${filledFields.length} 个字段`);
      } else {
        message.info('未能从描述中提取到结构化信息，请手动填写');
      }
    } catch (agentError) {
      console.warn('AI智能体提取失败，回退到传统正则提取:', agentError);
      // 智能体提取失败时，回退到传统正则提取
      try {
        const result = await nlpApi.extract({ text });
        const filledFields: string[] = [];

        if (result.city) {
          form.setFieldValue('city_name', result.city);
          filledFields.push('city_name');
          highlightExtractedField('city_name');
        }
        if (result.attraction) {
          form.setFieldValue('attraction', result.attraction);
          filledFields.push('attraction');
          highlightExtractedField('attraction');
        }
        if (result.budget) {
          form.setFieldValue('total_budget', result.budget);
          filledFields.push('total_budget');
          highlightExtractedField('total_budget');
        }
        if (result.people) {
          form.setFieldValue('traveler_count', result.people);
          filledFields.push('traveler_count');
          highlightExtractedField('traveler_count');
        }
        if (result.travel_days) {
          form.setFieldValue('travel_days', result.travel_days);
          filledFields.push('travel_days');
          highlightExtractedField('travel_days');
        }
        if (result.depart_time) {
          const date = parseNaturalDate(result.depart_time);
          if (date) {
            form.setFieldValue('travel_date', date);
            filledFields.push('travel_date');
            highlightExtractedField('travel_date');
          }
        }

        if (filledFields.length > 0) {
          setShowExtractSummary(true);
          message.success(`已提取信息，请确认并补充完整（共 ${filledFields.length} 个字段）`);
        } else {
          message.info('未能从描述中提取到结构化信息，请手动填写');
        }
      } catch (fallbackError) {
        message.error('提取失败，请手动填写');
        console.error('所有提取方式均失败:', fallbackError);
      }
    } finally {
      setExtracting(false);
    }
  };

  const handleSubmit = async (values: RequirementFormValues) => {
    setLoading(true);
    try {
      const response = await requirementApi.submit({
        user_id: currentUserId,
        requirement: {
          city_name: values.city_name,
          travel_days: values.travel_days,
          total_budget: values.total_budget,
          travel_type: values.travel_type,
          travel_date: values.travel_date.format('YYYY-MM-DD'),
          preferences: values.preferences
        }
      });

      // response已经是完整的响应对象，不需要再访问.data
      
            if (response.code === 200) {
        message.success('需求提交成功！');

        const requirementId = response.data.requirement_id;

        // 自动进行任务分解
        message.loading({ content: '正在智能规划行程...', key: 'decompose', duration: 0 });

        const decomposeResponse = await fetch('/api/v1/task/decompose', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            requirement_id: requirementId,
            structured_requirement: {
              city_name: values.city_name,
              travel_days: values.travel_days,
              total_budget: values.total_budget,
              travel_date: values.travel_date.format('YYYY-MM-DD'),
              traveler_count: values.traveler_count,
              preferences: values.preferences,
            }
          })
        });

        const decomposeData = await decomposeResponse.json();
        message.destroy('decompose');

        console.log('任务分解响应:', decomposeData);

          if (decomposeData.code === 200) {
          message.success('任务分解成功！正在生成专属行程...');
          setTimeout(() => {
            navigate(`/task/${decomposeData.data.task_id}`);
          }, 1500);
        } else {
          console.error('任务分解失败:', decomposeData);
          message.error(decomposeData.msg || '任务分解失败');
        }
      } else {
        message.error(response.msg || '提交失败');
      }
    } catch (error) {
      console.error('提交失败:', error);
      message.error('提交失败,请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <Card
        title={
          <Space>
            <CompassOutlined style={{ fontSize: 20, color: 'var(--stamp-blue, #4a7a8c)' }} />
            <span>智能旅游需求规划</span>
          </Space>
        }
      >
        {/* 智能提取提示 */}
        {showExtractSummary && (
          <Alert
            message={
              <Space>
              <FormOutlined style={{ fontSize: 16, color: 'var(--stamp-green, #6a8f6a)' }} />
                <Text strong>已智能提取到以下信息</Text>
              </Space>
            }
            description={
              <div style={{ marginTop: 8 }}>
                <Text type="secondary">请确认下方绿色高亮的字段是否正确，可手动修改后直接点击"提交需求"开始规划</Text>
              </div>
            }
            type="success"
            showIcon={false}
            closable
            onClose={() => setShowExtractSummary(false)}
            style={{ marginBottom: 16 }}
          />
        )}

        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{
            travel_days: 3,
            traveler_count: 2,
            travel_type: 'leisure',
            preferences: []
          }}
        >
          {/* 自然语言输入 */}
          <Form.Item
            name="natural_language"
            label={
              <Space>
              <FormOutlined style={{ color: 'var(--stamp-blue, #4a7a8c)' }} />
              <span>自然语言描述您的旅行需求</span>
            </Space>
            }
            tooltip="用日常语言描述您的旅行计划，AI将自动提取关键信息"
          >
            <TextArea
              placeholder={'试试这样说：\n"下周五去西安看兵马俑，两个人，预算两千五，玩三天"\n"暑假带爸妈去成都玩四天，预算五千，喜欢美食和自然风光"\n"明天坐高铁去上海玩三天，预算三千，一个人去迪士尼"'}
              rows={4}
              disabled={extracting}
              style={{ fontSize: 14 }}
            />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              icon={<CompassOutlined />}
              onClick={handleNaturalLanguageSubmit}
              loading={extracting}
              style={{ marginRight: '16px' }}
              size="large"
            >
              {extracting ? '正在理解...' : 'AI 智能提取'}
            </Button>
            <Button onClick={() => {
              form.resetFields();
              // ✅ 手动清空有默认值的字段
              form.setFieldsValue({
                travel_days: undefined,
                traveler_count: undefined,
                travel_type: undefined,
                preferences: []
              });
              setShowExtractSummary(false);
              setExtractedFields([]);
            }}>
              清除
            </Button>
          </Form.Item>

                    <Divider>
            <Space>
              <OrderedListOutlined style={{ color: 'var(--stamp-blue, #4a7a8c)' }} />
              <span>详细信息</span>
              <Text type="secondary" style={{ fontSize: 12 }}>（可手动修改AI提取的结果）</Text>
            </Space>
          </Divider>

          {/* 目的地城市和景点 */}
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="city_name"
                label="目的地城市"
                rules={[{ required: true, message: '请输入目的地城市' }]}
              >
                <Input
                  placeholder="例如:北京、上海、西安"
                  style={isFieldHighlighted('city_name') ? { borderColor: '#52c41a', backgroundColor: '#f6ffed' } : {}}
                  prefix={isFieldHighlighted('city_name') ? <Tag color="green" style={{ marginRight: -4 }}>已提取</Tag> : null}
                />
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item
                name="attraction"
                label="目的地景点（可选）"
              >
                <Input
                  placeholder="例如:兵马俑、故宫、西湖"
                  style={isFieldHighlighted('attraction') ? { borderColor: '#52c41a', backgroundColor: '#f6ffed' } : {}}
                  prefix={isFieldHighlighted('attraction') ? <Tag color="green" style={{ marginRight: -4 }}>已提取</Tag> : null}
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            {/* 出行天数 */}
            <Col span={8}>
              <Form.Item
                name="travel_days"
                label="出行天数"
                rules={[{ required: true, message: '请输入出行天数' }]}
              >
                <InputNumber
                  min={1} max={30} style={{
                    width: '100%',
                    ...(isFieldHighlighted('travel_days') ? { borderColor: '#52c41a', backgroundColor: '#f6ffed' } : {})
                  }}
                  addonAfter={isFieldHighlighted('travel_days') ? <Tag color="green" style={{ margin: 0 }}>已提取</Tag> : '天'}
                />
              </Form.Item>
            </Col>

            {/* 出行人数 */}
            <Col span={8}>
              <Form.Item
                name="traveler_count"
                label="出行人数"
                rules={[{ required: true, message: '请输入出行人数' }]}
              >
                <InputNumber
                  min={1} max={20} style={{
                    width: '100%',
                    ...(isFieldHighlighted('traveler_count') ? { borderColor: '#52c41a', backgroundColor: '#f6ffed' } : {})
                  }}
                  addonAfter={isFieldHighlighted('traveler_count') ? <Tag color="green" style={{ margin: 0 }}>已提取</Tag> : '人'}
                />
              </Form.Item>
            </Col>

            {/* 出行类型 */}
            <Col span={8}>
              <Form.Item
                name="travel_type"
                label="出行类型"
                rules={[{ required: true, message: '请选择出行类型' }]}
              >
                <Select style={isFieldHighlighted('travel_type') ? { borderColor: '#52c41a' } : {}}>
                  <Option value="leisure">休闲游</Option>
                  <Option value="family">家庭游</Option>
                  <Option value="adventure">探险游</Option>
                  <Option value="business">商务游</Option>
                  <Option value="culture">文化游</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>

          {/* 出行日期 */}
          <Form.Item
            name="travel_date"
            label="出行日期"
            rules={[{ required: true, message: '请选择出行日期' }]}
          >
            <DatePicker
              style={{
                width: '100%',
                ...(isFieldHighlighted('travel_date') ? { borderColor: '#52c41a', backgroundColor: '#f6ffed' } : {})
              }}
            />
          </Form.Item>

          {/* 总预算 */}
          <Form.Item
            name="total_budget"
            label="总预算(元)"
            rules={[{ required: true, message: '请输入总预算' }]}
          >
            <InputNumber
              min={0}
              style={{
                width: '100%',
                ...(isFieldHighlighted('total_budget') ? { borderColor: '#52c41a', backgroundColor: '#f6ffed' } : {})
              }}
              placeholder="例如:5000"
              addonAfter={isFieldHighlighted('total_budget') ? <Tag color="green" style={{ margin: 0 }}>已提取</Tag> : '元'}
            />
          </Form.Item>

          {/* 偏好 */}
          <Form.Item
            name="preferences"
            label={
              <Space>
                <span>偏好(可选)</span>
                {isFieldHighlighted('preferences') && <Tag color="green">AI已推荐</Tag>}
              </Space>
            }
          >
            <Select
              mode="tags"
              placeholder="请选择或输入偏好"
              style={isFieldHighlighted('preferences') ? { borderColor: '#52c41a' } : {}}
            >
              <Option value="历史古迹">历史古迹</Option>
              <Option value="自然风光">自然风光</Option>
              <Option value="美食探索">美食探索</Option>
              <Option value="购物">购物</Option>
              <Option value="文化体验">文化体验</Option>
              <Option value="户外运动">户外运动</Option>
            </Select>
          </Form.Item>

          {/* 提交按钮 */}
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              {loading ? '正在提交并规划行程...' : '提交需求'}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default RequirementForm;
