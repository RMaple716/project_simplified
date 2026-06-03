import React, { useState } from 'react';
import { Form, Input, InputNumber, DatePicker, Select, Button, Card, message, Row, Col, Divider } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { RootState } from '../store';
import { nlpApi, requirementApi } from '../services';
import { parseNaturalDate } from '../utils/helpers';
import type { Dayjs } from 'dayjs';

const { TextArea } = Input;
const { Option } = Select;

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

const RequirementForm: React.FC = () => {
  const navigate = useNavigate();
  const user = useSelector((state: RootState) => state.auth.user);
  const currentUserId = user?.user_id || 'anonymous';
  const [form] = Form.useForm<RequirementFormValues>();
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);

  const handleNaturalLanguageSubmit = async () => {
    const text = form.getFieldValue('natural_language');
    if (!text || text.trim().length === 0) {
      message.warning('请输入您的旅游需求');
      return;
    }

    setExtracting(true);
    try {
      const result = await nlpApi.extract({ text });
      // 将提取的结果填充到表单中
      if (result.city) {
        form.setFieldValue('city_name', result.city);
      }
      if (result.attraction) {
        form.setFieldValue('attraction', result.attraction);
      }
      if (result.budget) {
        form.setFieldValue('total_budget', result.budget);
      }
      if (result.people) {
        form.setFieldValue('traveler_count', result.people);
      }
      if (result.travel_days) {
        form.setFieldValue('travel_days', result.travel_days);
      }
      if (result.depart_time) {
        // 使用智能日期解析函数
        const date = parseNaturalDate(result.depart_time);
        if (date) {
          form.setFieldValue('travel_date', date);
        } else {
          console.warn('无法解析日期:', result.depart_time);
        }
      }

      message.success('已提取信息,请确认并补充完整');
    } catch (error) {
      message.error('提取失败,请手动填写');
      console.error('NLP提取失败:', error);
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
        message.success('✅ 需求提交成功！');

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
          message.success('🎉 任务分解成功！正在生成专属行程...');
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
      <Card title="旅游需求规划">
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
            label="自然语言描述(可选)"
          >
            <TextArea
              placeholder="例如:下周五去西安看兵马俑,两个人,预算两千五"
              rows={3}
              disabled={extracting}
            />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              onClick={handleNaturalLanguageSubmit}
              loading={extracting}
              style={{ marginRight: '16px' }}
            >
              智能提取
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
            }}>
              清除
            </Button>
          </Form.Item>

          <Divider>详细信息</Divider>

          {/* 目的地城市和景点 */}
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="city_name"
                label="目的地城市"
                rules={[{ required: true, message: '请输入目的地城市' }]}
              >
                <Input placeholder="例如:北京、上海、西安" />
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item
                name="attraction"
                label="目的地景点（可选）"
              >
                <Input placeholder="例如:兵马俑、故宫、西湖" />
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
                <InputNumber min={1} max={30} style={{ width: '100%' }} />
              </Form.Item>
            </Col>

            {/* 出行人数 */}
            <Col span={8}>
              <Form.Item
                name="traveler_count"
                label="出行人数"
                rules={[{ required: true, message: '请输入出行人数' }]}
              >
                <InputNumber min={1} max={20} style={{ width: '100%' }} />
              </Form.Item>
            </Col>

            {/* 出行类型 */}
            <Col span={8}>
              <Form.Item
                name="travel_type"
                label="出行类型"
                rules={[{ required: true, message: '请选择出行类型' }]}
              >
                <Select>
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
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>

          {/* 总预算 */}
          <Form.Item
            name="total_budget"
            label="总预算(元)"
            rules={[{ required: true, message: '请输入总预算' }]}
          >
            <InputNumber min={0} style={{ width: '100%' }} placeholder="例如:5000" />
          </Form.Item>

          {/* 偏好 */}
          <Form.Item
            name="preferences"
            label="偏好(可选)"
          >
            <Select mode="tags" placeholder="请选择或输入偏好">
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
              提交需求
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default RequirementForm;
