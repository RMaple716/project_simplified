import React, { useEffect, useState } from 'react';
import { 
  Typography, 
  Button, 
  Card, 
  Timeline, 
  Tag, 
  Space, 
  Descriptions,
  Divider,
  Spin,
  Empty,
  message,
  Statistic,
  Row,
  Col,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  TimePicker,
  Popconfirm
} from 'antd';
import { 
  ArrowLeftOutlined,
  EnvironmentOutlined,
  CalendarOutlined,
  DollarOutlined,
  ClockCircleOutlined,
  HomeOutlined,
  RestOutlined,
  CameraOutlined,
  FileTextOutlined,
  EditOutlined,
  DeleteOutlined,
  PlusOutlined,
  SaveOutlined,
  CarOutlined
} from '@ant-design/icons';
import NegotiationVisualizer from '../components/NegotiationVisualizer';
import { extractEventsFromItinerary } from '../services/negotiationApi';
import { useNavigate, useParams } from 'react-router-dom';
import { itineraryApi, Itinerary } from '../services/itineraryApi';
import dayjs from 'dayjs';
import WeatherInfo from '../components/weatherinfo';
import { NavigationMapView, DayMultiRouteMap } from '../components/NavigationMapView';
import type { NavigationData, LocationPoint, RouteSegment } from '../components/NavigationMapView';
import { formatLocation, extractLatLng } from '../utils/locationHelper';
const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

// 景点类型定义
interface Attraction {
  attraction_id: string;
  name: string;
  city_name: string;
  location: string;
  description?: string;
  recommended_duration?: string;
  visit_time_slot?: 'morning' | 'afternoon' | 'evening';
  visit_time?: string;
  visit_duration?: string;
  start_time?: string;
  end_time?: string;
  ticket_price?: number;
  rating?: number;
  opening_hours?: string;
  tags?: string[];
}

// 餐饮类型定义
interface Meal {
  restaurant_id: string;
  name: string;
  city_name: string;
  location: string;
  cuisine_type?: string;
  avg_price?: number;
  rating?: number;
  specialties?: string[];
  meal_type?: string;
  meal_time?: string;
  time?: string;
  start_time?: string;
  end_time?: string;
  duration?: string;
}

// 景点编辑表单组件
const AttractionForm: React.FC<{
  initialValues?: Attraction;
  onSubmit: (values: Attraction) => void;
  onCancel: () => void;
}> = ({ initialValues, onSubmit, onCancel }) => {
  const [form] = Form.useForm();

    /** 判断字符串是否为有效的 HH:mm 时间格式 */
  const isValidTimeFormat = (str: string): boolean => /^\d{1,2}:\d{2}$/.test(str);

  useEffect(() => {
    if (initialValues) {
      // visit_time 可能是 "上午"/"下午"/"晚上" 等中文时段，不是有效 HH:mm 格式
      // 此时用 start_time 作为 TimePicker 的初始值
      const rawVisitTime = initialValues.visit_time || '';
      const timeValue = isValidTimeFormat(rawVisitTime)
        ? dayjs(rawVisitTime, 'HH:mm')
        : initialValues.start_time && isValidTimeFormat(initialValues.start_time)
          ? dayjs(initialValues.start_time, 'HH:mm')
          : null;
      form.setFieldsValue({
        ...initialValues,
        visit_time: timeValue,
      });
    }
  }, [initialValues, form]);

  const handleSubmit = () => {
    form.validateFields().then((values) => {
      const formattedValues = {
        ...values,
        visit_time: values.visit_time ? values.visit_time.format('HH:mm') : undefined,
      };
      onSubmit(formattedValues);
    });
  };

  return (
    <Form form={form} layout="vertical">
      <Form.Item
        name="name"
        label="景点名称"
        rules={[{ required: true, message: '请输入景点名称' }]}
      >
        <Input placeholder="例如：故宫博物院" />
      </Form.Item>
      
      <Form.Item
        name="visit_time"
        label="游览时间"
      >
        <TimePicker format="HH:mm" placeholder="选择时间" style={{ width: '100%' }} />
      </Form.Item>
      
      <Form.Item
        name="visit_duration"
        label="游览时长"
      >
        <Input placeholder="例如：2小时" />
      </Form.Item>
      
      <Form.Item
        name="ticket_price"
        label="门票价格（元）"
      >
        <InputNumber min={0} style={{ width: '100%' }} placeholder="0" />
      </Form.Item>
      
      <Form.Item
        name="location"
        label="地点"
      >
        <Input placeholder="例如：北京市东城区" />
      </Form.Item>
      
      <Form.Item
        name="description"
        label="描述"
      >
        <TextArea rows={2} placeholder="景点简介..." />
      </Form.Item>
      
      <Form.Item
        name="rating"
        label="评分"
      >
        <InputNumber min={0} max={5} step={0.1} style={{ width: '100%' }} placeholder="0-5" />
      </Form.Item>
      
      <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
        <Space>
          <Button onClick={onCancel}>取消</Button>
          <Button type="primary" onClick={handleSubmit}>
            确定
          </Button>
        </Space>
      </Form.Item>
    </Form>
  );
};

// 餐饮编辑表单组件
const MealForm: React.FC<{
  initialValues?: Meal;
  onSubmit: (values: Meal) => void;
  onCancel: () => void;
}> = ({ initialValues, onSubmit, onCancel }) => {
  const [form] = Form.useForm();

    /** 判断字符串是否为有效的 HH:mm 时间格式 */
  const isValidTimeFormat = (str: string): boolean => /^\d{1,2}:\d{2}$/.test(str);

  useEffect(() => {
    if (initialValues) {
      // meal_time 可能是 "中午"/"早上"/"晚上" 等中文时段，不是有效 HH:mm 格式
      // 此时用 start_time 或 time 字段作为 TimePicker 的初始值
      const rawMealTime = initialValues.meal_time || '';
      const timeValue = isValidTimeFormat(rawMealTime)
        ? dayjs(rawMealTime, 'HH:mm')
        : initialValues.start_time && isValidTimeFormat(initialValues.start_time)
          ? dayjs(initialValues.start_time, 'HH:mm')
          : initialValues.time && isValidTimeFormat(initialValues.time)
            ? dayjs(initialValues.time, 'HH:mm')
            : null;
      form.setFieldsValue({
        ...initialValues,
        meal_time: timeValue,
      });
    }
  }, [initialValues, form]);

  const handleSubmit = () => {
    form.validateFields().then((values) => {
      const formattedValues = {
        ...values,
        meal_time: values.meal_time ? values.meal_time.format('HH:mm') : undefined,
      };
      onSubmit(formattedValues);
    });
  };

  return (
    <Form form={form} layout="vertical">
      <Form.Item
        name="name"
        label="餐厅名称"
        rules={[{ required: true, message: '请输入餐厅名称' }]}
      >
        <Input placeholder="例如：全聚德烤鸭店" />
      </Form.Item>
      
      <Form.Item
        name="meal_type"
        label="餐次"
      >
        <Select placeholder="选择餐次">
          <Select.Option value="breakfast">早餐</Select.Option>
          <Select.Option value="lunch">午餐</Select.Option>
          <Select.Option value="dinner">晚餐</Select.Option>
        </Select>
      </Form.Item>
      
      <Form.Item
        name="meal_time"
        label="用餐时间"
      >
        <TimePicker format="HH:mm" placeholder="选择时间" style={{ width: '100%' }} />
      </Form.Item>
      
      <Form.Item
        name="cuisine_type"
        label="菜系"
      >
        <Input placeholder="例如：北京菜" />
      </Form.Item>
      
      <Form.Item
        name="avg_price"
        label="人均价格（元）"
      >
        <InputNumber min={0} style={{ width: '100%' }} placeholder="0" />
      </Form.Item>
      
      <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
        <Space>
          <Button onClick={onCancel}>取消</Button>
          <Button type="primary" onClick={handleSubmit}>
            确定
          </Button>
        </Space>
      </Form.Item>
    </Form>
  );
};

// 景点卡片组件
const AttractionCard: React.FC<{ 
  attraction: any; 
  index: number;
  dayIndex: number;
  onEdit: (dayIndex: number, attractionIndex: number) => void;
  onDelete: (dayIndex: number, attractionIndex: number) => void;
}> = ({ attraction, index, dayIndex, onEdit, onDelete }) => (
  <Card 
    size="small" 
    style={{ marginBottom: 8 }}
    styles={{ body: { padding: '12px' } }}
    extra={
      <Space size="small">
        <Button 
          type="text" 
          size="small" 
          icon={<EditOutlined />}
          onClick={() => onEdit(dayIndex, index)}
        />
        <Popconfirm
          title="确定删除此景点吗？"
          onConfirm={() => onDelete(dayIndex, index)}
          okText="确定"
          cancelText="取消"
        >
          <Button 
            type="text" 
            size="small" 
            danger
            icon={<DeleteOutlined />}
          />
        </Popconfirm>
      </Space>
    }
  >
    <Space direction="vertical" size="small" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>{attraction.name}</Text>
        {attraction.rating && (
          <Tag color="gold">⭐ {attraction.rating}</Tag>
        )}
      </div>
      {attraction.description && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {attraction.description}
        </Text>
      )}

                            {(() => {
        // 优先展示具体时间 HH:mm-HH:mm，其次 visit_time（上午/下午/晚上）
        const timeDisplay = attraction.start_time
          ? `${attraction.start_time}${attraction.end_time ? `-${attraction.end_time}` : ''}`
          : attraction.visit_time || '';
        if (!timeDisplay) return null;
        return (
          <Tag icon={<ClockCircleOutlined />} color="blue">
            {timeDisplay}
          </Tag>
        );
      })()}
        {attraction.visit_duration && (
          <Tag icon={<ClockCircleOutlined />}>
            {attraction.visit_duration}
          </Tag>
        )}
        {attraction.ticket_price && (
          <Tag icon={<DollarOutlined />} color="green">
            ¥{attraction.ticket_price}
          </Tag>
        )}
         {attraction.location && (
          <Tag icon={<EnvironmentOutlined />}>
            {formatLocation(attraction.location)}
          </Tag>
)}
    </Space>
  </Card>
);

// 餐饮卡片组件
const MealCard: React.FC<{ 
  meal: any; 
  index: number;
  dayIndex: number;
  onEdit: (dayIndex: number, mealIndex: number) => void;
  onDelete: (dayIndex: number, mealIndex: number) => void;
}> = ({ meal, index, dayIndex, onEdit, onDelete }) => (
  <Card 
    size="small" 
    style={{ marginBottom: 8 }}
    styles={{ body: { padding: '12px' } }}
    extra={
      <Space size="small">
        <Button 
          type="text" 
          size="small" 
          icon={<EditOutlined />}
          onClick={() => onEdit(dayIndex, index)}
        />
        <Popconfirm
          title="确定删除此餐饮吗？"
          onConfirm={() => onDelete(dayIndex, index)}
          okText="确定"
          cancelText="取消"
        >
          <Button 
            type="text" 
            size="small" 
            danger
            icon={<DeleteOutlined />}
          />
        </Popconfirm>
      </Space>
    }
  >
    <Space direction="vertical" size="small" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>{meal.name || meal.restaurant_name}</Text>
        {meal.meal_type && (
          <Tag color="orange">
            {meal.meal_type === 'breakfast' ? '早餐' : 
             meal.meal_type === 'lunch' ? '午餐' : '晚餐'}
          </Tag>
        )}
      </div>
      {meal.cuisine_type && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {meal.cuisine_type}
        </Text>
            )}
      <Space size="small">
        {(() => {
          // 优先显示具体用餐时间 HH:mm，其次 meal_time（早上/中午/晚上）
          const mealTimeDisplay = meal.start_time || meal.time || meal.meal_time || '';
          if (!mealTimeDisplay) return null;
          return (
            <Tag icon={<ClockCircleOutlined />} color="blue">
              {mealTimeDisplay}
            </Tag>
          );
        })()}
        {meal.avg_price && (
          <Tag icon={<DollarOutlined />} color="green">
            ¥{meal.avg_price}/人
          </Tag>
        )}
      </Space>
    </Space>
  </Card>
);

// 住宿信息组件
const HotelInfo: React.FC<{ hotel: any }> = ({ hotel }) => (
  <Card 
    size="small"
    style={{ marginBottom: 8, backgroundColor: '#f6ffed' }}
    styles={{ body: { padding: '12px' } }}
  >
    <Space direction="vertical" size="small" style={{ width: '100%' }}>
      <Text strong><HomeOutlined /> 住宿安排</Text>
      <Text>{hotel.name}</Text>
            {hotel.location && (
  <Text type="secondary">
    <EnvironmentOutlined style={{ marginRight: 4 }} />
    {formatLocation(hotel.location)}
  </Text>
)}
      {hotel.price_per_night && (
        <Text type="secondary">¥{hotel.price_per_night}/晚</Text>
      )}
      {hotel.rating && (
        <Tag color="gold">⭐ {hotel.rating}</Tag>
      )}
      {hotel.amenities && hotel.amenities.length > 0 && (
        <div>
          {hotel.amenities.map((amenity: string, idx: number) => (
            <Tag key={idx} style={{ marginBottom: 4 }}>
              {amenity}
            </Tag>
          ))}
        </div>
      )}
    </Space>
  </Card>
);

const convertTransportToNavigationData = (transport: any): NavigationData | null => {
  if (!transport) return null;

  const from = transport.from_location || transport.from || transport.origin || '';
  const to = transport.to_location || transport.to || transport.destination || '';
  const type = transport.mode || transport.type || 'driving';

  const fromStr = formatLocation(from);
  const toStr = formatLocation(to);

  if (!fromStr || !toStr) return null;

  return {
    from: fromStr,
    to: toStr,
    type,
    fromLocation: extractLatLng(transport.from_location) || extractLatLng(transport.fromLocation) || null,
    toLocation: extractLatLng(transport.to_location) || extractLatLng(transport.toLocation) || null,
  };
};
const extractLocationCoords = (item: any): string | null => {
  if (!item) return null;
  const latLng = extractLatLng(item.location);
  if (latLng) return `${latLng.lng},${latLng.lat}`;
  return null;
};


// ==================== 每日行程内容组件 ====================
const DayPlanContent: React.FC<{ 
  dayPlan: any;
  dayIndex: number;
  cityName?: string;
  onEditAttraction: (dayIndex: number, attractionIndex: number) => void;
  onDeleteAttraction: (dayIndex: number, attractionIndex: number) => void;
  onAddAttraction: (dayIndex: number) => void;
  onEditMeal: (dayIndex: number, mealIndex: number) => void;
  onDeleteMeal: (dayIndex: number, mealIndex: number) => void;
  onAddMeal: (dayIndex: number) => void;
  onEditNotes: (dayIndex: number) => void;
}> = ({ 
  dayPlan, 
  dayIndex,
  cityName,
  onEditAttraction,
  onDeleteAttraction,
  onAddAttraction,
  onEditMeal,
  onDeleteMeal,
  onAddMeal,
  onEditNotes
}) => {
  const timelineItems = [];

  if (dayPlan.weather) {
    timelineItems.push({
      color: 'cyan',
      children: <WeatherInfo weather={dayPlan.weather} />
    });
  }

// ==================== 构造多路段数据 ====================
const navData = convertTransportToNavigationData(dayPlan.transport);
if (navData && dayPlan.attractions && dayPlan.attractions.length > 0) {
  // 收集所有途经点的坐标
  const locationPoints: LocationPoint[] = [];

    const allAttractions = dayPlan.attractions
    .map((attr: any, idx: number): { name: string; lat: number; lng: number } | null => {
      const coords = extractLocationCoords(attr);
      if (coords) {
        const [lng, lat] = coords.split(',').map(Number);
        locationPoints.push({
          name: attr.name || `景点${idx + 1}`,
          lat, lng,
          type: 'attraction' as const,
          day: dayPlan.day
        });
        return { name: attr.name || `景点${idx + 1}`, lat, lng };
      }
      return null;
    })
    .filter((item: { name: string; lat: number; lng: number } | null): item is { name: string; lat: number; lng: number } => item !== null);

  // 如果有酒店，也加入
  if (dayPlan.hotel) {
    const hotelCoords = extractLocationCoords(dayPlan.hotel);
    if (hotelCoords) {
      const [lng, lat] = hotelCoords.split(',').map(Number);
      locationPoints.push({
        name: dayPlan.hotel.name || '住宿',
        lat, lng,
        type: 'hotel' as const,
        day: dayPlan.day
      });
    }
  }


    if (allAttractions.length >= 2) {
    
    const rawMode = (dayPlan.transport?.mode || dayPlan.transport?.type || 'driving');
    const defaultMode = (rawMode === 'riding' ? 'bicycling' : rawMode) as 'driving' | 'walking' | 'bicycling' | 'transit';

    const segments: RouteSegment[] = [];
    for (let i = 0; i < allAttractions.length - 1; i++) {
      const from = allAttractions[i];
      const to = allAttractions[i + 1];


      const segmentTransport = dayPlan.transport?.segments?.[i];
      const rawSegMode = (segmentTransport?.mode || segmentTransport?.type || defaultMode);
      const mode = (rawSegMode === 'riding' ? 'bicycling' : rawSegMode) as 'driving' | 'walking' | 'bicycling' | 'transit';

      segments.push({
        from: from.name || `景点${i + 1}`,
        to: to.name || `景点${i + 2}`,
        type: mode,
        fromLocation: { lat: from.lat, lng: from.lng },
        toLocation: { lat: to.lat, lng: to.lng },
        cityName: cityName
      });
    }

        // 使用按需加载的多路段地图组件
    timelineItems.push({
      color: 'blue',
      dot: <CarOutlined />,
      children: (
        <DayMultiRouteMap
          segments={segments}
          allLocations={locationPoints.length > 0 ? locationPoints : undefined}
          cityName={cityName}
        />
      )
    });
  } else {
    // 只有一个景点，使用单路段地图
    timelineItems.push({
      color: 'blue',
      dot: <CarOutlined />,
      children: (
        <NavigationMapView
          navigationData={navData}
          allLocations={locationPoints.length > 0 ? locationPoints : undefined}
          cityName={cityName}
        />
      )
    });
  }
} else if (navData) {
  // 有 transport 数据但没有景点
  const locationPoints: LocationPoint[] = [];
  if (dayPlan.hotel) {
    const hotelCoords = extractLocationCoords(dayPlan.hotel);
    if (hotelCoords) {
      const [lng, lat] = hotelCoords.split(',').map(Number);
      locationPoints.push({
        name: dayPlan.hotel.name || '住宿',
        lat, lng,
        type: 'hotel' as const,
        day: dayPlan.day
      });
    }
  }
  timelineItems.push({
    color: 'blue',
    dot: <CarOutlined />,
    children: (
      <NavigationMapView
        navigationData={navData}
        allLocations={locationPoints.length > 0 ? locationPoints : undefined}
        cityName={cityName}
      />
    )
  });
}

  if (dayPlan.attractions && dayPlan.attractions.length > 0) {
    timelineItems.push({
      color: 'green',
      dot: <CameraOutlined />,
      children: (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <Text strong><CameraOutlined /> 景点游览</Text>
            <Button 
              type="dashed" 
              size="small" 
              icon={<PlusOutlined />}
              onClick={() => onAddAttraction(dayIndex)}
            >
              添加景点
            </Button>
          </div>
          <div style={{ marginTop: 8 }}>
            {dayPlan.attractions.map((attraction: any, idx: number) => (
              <AttractionCard 
                key={idx} 
                attraction={attraction} 
                index={idx}
                dayIndex={dayIndex}
                onEdit={onEditAttraction}
                onDelete={onDeleteAttraction}
              />
            ))}
          </div>
        </div>
      )
    });
  } else {
    timelineItems.push({
      color: 'green',
      dot: <CameraOutlined />,
      children: (
        <Button 
          type="dashed" 
          block
          icon={<PlusOutlined />}
          onClick={() => onAddAttraction(dayIndex)}
        >
          添加景点
        </Button>
      )
    });
  }

  if (dayPlan.meals && dayPlan.meals.length > 0) {
    timelineItems.push({
      color: 'orange',
      dot: <RestOutlined />,
      children: (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <Text strong><RestOutlined /> 餐饮安排</Text>
            <Button 
              type="dashed" 
              size="small" 
              icon={<PlusOutlined />}
              onClick={() => onAddMeal(dayIndex)}
            >
              添加餐饮
            </Button>
          </div>
          <div style={{ marginTop: 8 }}>
            {dayPlan.meals.map((meal: any, idx: number) => (
              <MealCard 
                key={idx} 
                meal={meal} 
                index={idx}
                dayIndex={dayIndex}
                onEdit={onEditMeal}
                onDelete={onDeleteMeal}
              />
            ))}
          </div>
        </div>
      )
    });
  } else {
    timelineItems.push({
      color: 'orange',
      dot: <RestOutlined />,
      children: (
        <Button 
          type="dashed" 
          block
          icon={<PlusOutlined />}
          onClick={() => onAddMeal(dayIndex)}
        >
          添加餐饮
        </Button>
      )
    });
  }

  if (dayPlan.hotel) {
    timelineItems.push({
      color: 'purple',
      children: <HotelInfo hotel={dayPlan.hotel} />
    });
  }

  timelineItems.push({
    color: 'gray',
    dot: <FileTextOutlined />,
    children: (
      <Card size="small" styles={{ body: { padding: '12px' } }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Text type="secondary"><FileTextOutlined /> 备注：</Text>
          <Button 
            type="text" 
            size="small" 
            icon={<EditOutlined />}
            onClick={() => onEditNotes(dayIndex)}
          />
        </div>
        <div style={{ marginTop: 4 }}>
          {dayPlan.notes ? (
            <Text>{dayPlan.notes}</Text>
          ) : (
            <Text type="secondary">暂无备注</Text>
          )}
        </div>
      </Card>
    )
  });

  return <Timeline items={timelineItems} />;
};

// ==================== 主页面组件 ====================
const ItineraryDetail: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  
  
  const [editAttractionModal, setEditAttractionModal] = useState<{
    visible: boolean;
    dayIndex: number;
    attractionIndex?: number;
    initialValues?: Attraction;
  }>({ visible: false, dayIndex: -1 });
  
  const [editMealModal, setEditMealModal] = useState<{
    visible: boolean;
    dayIndex: number;
    mealIndex?: number;
    initialValues?: Meal;
  }>({ visible: false, dayIndex: -1 });
  
  const [editNotesModal, setEditNotesModal] = useState<{
    visible: boolean;
    dayIndex: number;
    notes?: string;
  }>({ visible: false, dayIndex: -1 });

  useEffect(() => {
    if (id) {
      fetchItineraryDetail(id);
    }
  }, [id]);

  const fetchItineraryDetail = async (itineraryId: string) => {
    try {
      setLoading(true);
      const response = await itineraryApi.getById(itineraryId);
      
      if ((response as any).code === 200) {
        setItinerary((response as any).data);
      } else {
        message.error((response as any).msg || '获取行程详情失败');
      }
    } catch (error) {
      console.error('获取行程详情失败:', error);
      message.error('获取行程详情失败');
    } finally {
      setLoading(false);
    }
  };

  const saveItinerary = async () => {
    if (!itinerary || !id) return;
    
    try {
      setSaving(true);
      const response = await itineraryApi.update(id, {
        title: itinerary.title,
        day_plans: itinerary.day_plans,
      });
      
      if ((response as any).code === 200) {
        message.success('保存成功');
        const savedData = (response as any).data;
        setItinerary({
          ...itinerary,                      
          title: savedData.title,            
          day_plans: savedData.day_plans,
          status: savedData.status,
          updated_at: savedData.updated_at,
        });
      } else {
        message.error((response as any).msg || '保存失败');
      }
    } catch (error) {
      console.error('保存失败:', error);
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleEditAttraction = (dayIndex: number, attractionIndex: number) => {
    const attraction = itinerary?.day_plans?.[dayIndex]?.attractions?.[attractionIndex];
    setEditAttractionModal({
      visible: true,
      dayIndex,
      attractionIndex,
      initialValues: attraction,
    });
  };

  const handleAddAttraction = (dayIndex: number) => {
    setEditAttractionModal({
      visible: true,
      dayIndex,
    });
  };

  const handleDeleteAttraction = (dayIndex: number, attractionIndex: number) => {
    if (!itinerary || !itinerary.day_plans) return;
    
    const newDayPlans = [...itinerary.day_plans];
    const attractions = [...(newDayPlans[dayIndex].attractions || [])];
    attractions.splice(attractionIndex, 1);
    newDayPlans[dayIndex] = {
      ...newDayPlans[dayIndex],
      attractions,
    };
    
    setItinerary({
      ...itinerary,
      day_plans: newDayPlans,
    });
    
    message.success('已删除景点');
  };

  const handleSubmitAttraction = (values: Attraction) => {
    if (!itinerary || !itinerary.day_plans) return;
    
    const newDayPlans = [...itinerary.day_plans];
    const currentDayPlan = { ...newDayPlans[editAttractionModal.dayIndex] };
    const attractions = [...(currentDayPlan.attractions || [])];
    
    if (editAttractionModal.attractionIndex !== undefined) {
      attractions[editAttractionModal.attractionIndex] = values;
    } else {
      attractions.push(values);
    }
    newDayPlans[editAttractionModal.dayIndex] = {
      ...currentDayPlan,
      attractions,
    };
    
    setItinerary({
      ...itinerary,
      day_plans: newDayPlans,
    });
    
    setEditAttractionModal({ visible: false, dayIndex: -1 });
    message.success(editAttractionModal.attractionIndex !== undefined ? '修改成功' : '添加成功');
  };

  const handleEditMeal = (dayIndex: number, mealIndex: number) => {
    const meal = itinerary?.day_plans?.[dayIndex]?.meals?.[mealIndex];
    setEditMealModal({
      visible: true,
      dayIndex,
      mealIndex,
      initialValues: meal,
    });
  };

  const handleAddMeal = (dayIndex: number) => {
    setEditMealModal({
      visible: true,
      dayIndex,
    });
  };

  const handleDeleteMeal = (dayIndex: number, mealIndex: number) => {
    if (!itinerary || !itinerary.day_plans) return;
    
    const newDayPlans = [...itinerary.day_plans];
    const meals = [...(newDayPlans[dayIndex].meals || [])];
    meals.splice(mealIndex, 1);
    newDayPlans[dayIndex] = {
      ...newDayPlans[dayIndex],
      meals,
    };
    
    setItinerary({
      ...itinerary,
      day_plans: newDayPlans,
    });
    
    message.success('已删除餐饮');
  };

  const handleSubmitMeal = (values: Meal) => {
    if (!itinerary || !itinerary.day_plans) return;
    
    const newDayPlans = [...itinerary.day_plans];
    const currentDayPlan = { ...newDayPlans[editMealModal.dayIndex] };
    const meals = [...(currentDayPlan.meals || [])];
    
    if (editMealModal.mealIndex !== undefined) {
      meals[editMealModal.mealIndex] = values;
    } else {
      meals.push(values);
    }
    
    newDayPlans[editMealModal.dayIndex] = {
      ...currentDayPlan,
      meals,
    };
    
    setItinerary({
      ...itinerary,
      day_plans: newDayPlans,
    });
    
    setEditMealModal({ visible: false, dayIndex: -1 });
    message.success(editMealModal.mealIndex !== undefined ? '修改成功' : '添加成功');
  };

  const handleEditNotes = (dayIndex: number) => {
    const notes = itinerary?.day_plans?.[dayIndex]?.notes;
    setEditNotesModal({
      visible: true,
      dayIndex,
      notes,
    });
  };

  const handleSubmitNotes = () => {
    if (!itinerary || !itinerary.day_plans) return;
    
    const form = document.querySelector('#notesForm') as HTMLFormElement;
    if (form) {
      const formData = new FormData(form);
      const notes = formData.get('notes') as string;
      
      const newDayPlans = [...itinerary.day_plans];
      newDayPlans[editNotesModal.dayIndex] = {
        ...newDayPlans[editNotesModal.dayIndex],
        notes,
      };
      
      setItinerary({
        ...itinerary,
        day_plans: newDayPlans,
      });
      
      setEditNotesModal({ visible: false, dayIndex: -1 });
      message.success('备注已更新');
    }
  };

  const handleDeleteItinerary = async () => {
    if (!id) return;
    
    try {
      const response = await itineraryApi.delete(id);
      if ((response as any).code === 200) {
        message.success('行程已删除');
        navigate('/itineraries');
      } else {
        message.error((response as any).msg || '删除失败');
      }
    } catch (error) {
      console.error('删除失败:', error);
      message.error('删除失败');
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '48px', textAlign: 'center' }}>
        <Spin size="large" tip="加载行程详情..." />
      </div>
    );
  }

  if (!itinerary) {
    return (
      <div style={{ padding: '48px' }}>
        <Empty description="行程不存在或已被删除">
          <Button type="primary" onClick={() => navigate('/itineraries')}>
            返回行程列表
          </Button>
        </Empty>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <Button 
        icon={<ArrowLeftOutlined />} 
        onClick={() => navigate('/itineraries')}
        style={{ marginBottom: 16 }}
      >
        返回列表
      </Button>

      <Card style={{ marginBottom: 24 }}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={16}>
            <Title level={3} style={{ margin: 0 }}>
              {itinerary.title || `${itinerary.city_name} ${itinerary.travel_days}日游`}
            </Title>
            <Paragraph type="secondary" style={{ marginTop: 8 }}>
              创建于 {itinerary.created_at ? new Date(itinerary.created_at).toLocaleDateString() : '未知'}
            </Paragraph>
          </Col>
          <Col xs={24} md={8}>
            <Row gutter={[8, 8]}>
              <Col span={12}>
                <Statistic
                  title="总预算"
                  value={itinerary.total_budget}
                  prefix="¥"
                  valueStyle={{ fontSize: 18 }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="天数"
                  value={itinerary.travel_days}
                  suffix="天"
                />
              </Col>
            </Row>
          </Col>
        </Row>
        
        <Divider style={{ margin: '16px 0' }} />
        
        <Descriptions column={{ xs: 1, sm: 2, md: 3 }} size="small">
          <Descriptions.Item label={<><EnvironmentOutlined /> 目的地</>}>
            {itinerary.city_name}
          </Descriptions.Item>
          <Descriptions.Item label={<><CalendarOutlined /> 行程天数</>}>
            {itinerary.travel_days} 天
          </Descriptions.Item>
          <Descriptions.Item label={<><DollarOutlined /> 总预算</>}>
            ¥{itinerary.total_budget}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={
              itinerary.status === 'completed' ? 'green' :
              itinerary.status === 'draft' ? 'blue' : 'default'
            }>
              {itinerary.status === 'completed' ? '已完成' :
               itinerary.status === 'draft' ? '草稿' : itinerary.status}
            </Tag>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 每日行程时间轴 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <Title level={4} style={{ margin: 0 }}>
          <CalendarOutlined /> 每日行程安排
        </Title>
        <Space>
          <Button 
            type="primary" 
            icon={<SaveOutlined />} 
            onClick={saveItinerary}
            loading={saving}
          >
            保存修改
          </Button>
        </Space>
            </div>

      {/* ===== 协商过程可视化（放在每日行程之前，作为"幕后故事"） ===== */}
      <NegotiationVisualizer
        events={extractEventsFromItinerary(itinerary)}
        showFullPanel={true}
      />

      {itinerary.day_plans && itinerary.day_plans.length > 0 ? (
        itinerary.day_plans.map((dayPlan: any, index: number) => (
          <Card 
            key={index}
            title={
              <Space>
                <Tag color="blue">第{dayPlan.day}天</Tag>
                <Text>{dayPlan.date}</Text>
              </Space>
            }
            style={{ marginBottom: 16 }}
            styles={{ header: { backgroundColor: '#fafafa' } }}
          >
            <DayPlanContent 
              dayPlan={dayPlan} 
              dayIndex={index}
              cityName={itinerary.city_name}
              onEditAttraction={handleEditAttraction}
              onDeleteAttraction={handleDeleteAttraction}
              onAddAttraction={handleAddAttraction}
              onEditMeal={handleEditMeal}
              onDeleteMeal={handleDeleteMeal}
              onAddMeal={handleAddMeal}
              onEditNotes={handleEditNotes}
            />
          </Card>
        ))
      ) : (
        <Empty description="暂无行程安排" />
      )}

      <Divider />
      <Space>
        <Button type="primary" onClick={() => navigate('/itineraries')}>
          返回行程列表
        </Button>
        <Popconfirm
          title="确定删除此行程吗？"
          description="删除后无法恢复"
          onConfirm={handleDeleteItinerary}
          okText="确定"
          cancelText="取消"
          okButtonProps={{ danger: true }}
        >
          <Button danger>删除行程</Button>
        </Popconfirm>
      </Space>

      {/* 景点编辑弹窗 */}
      <Modal
        title={editAttractionModal.attractionIndex !== undefined ? '编辑景点' : '添加景点'}
        open={editAttractionModal.visible}
        onCancel={() => setEditAttractionModal({ visible: false, dayIndex: -1 })}
        footer={null}
        width={600}
      >
        <AttractionForm
          initialValues={editAttractionModal.initialValues}
          onSubmit={handleSubmitAttraction}
          onCancel={() => setEditAttractionModal({ visible: false, dayIndex: -1 })}
        />
      </Modal>

      {/* 餐饮编辑弹窗 */}
      <Modal
        title={editMealModal.mealIndex !== undefined ? '编辑餐饮' : '添加餐饮'}
        open={editMealModal.visible}
        onCancel={() => setEditMealModal({ visible: false, dayIndex: -1 })}
        footer={null}
        width={600}
      >
        <MealForm
          initialValues={editMealModal.initialValues}
          onSubmit={handleSubmitMeal}
          onCancel={() => setEditMealModal({ visible: false, dayIndex: -1 })}
        />
      </Modal>

      {/* 备注编辑弹窗 */}
      <Modal
        title="编辑备注"
        open={editNotesModal.visible}
        onOk={handleSubmitNotes}
        onCancel={() => setEditNotesModal({ visible: false, dayIndex: -1 })}
        okText="保存"
        cancelText="取消"
      >
        <Form id="notesForm" layout="vertical">
          <Form.Item name="notes" initialValue={editNotesModal.notes}>
            <TextArea rows={4} placeholder="输入备注信息..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ItineraryDetail;