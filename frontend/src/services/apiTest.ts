/**
 * API测试示例
 * 用于演示如何使用各个API模块
 */

import { 
  requirementApi, 
  taskApi, 
  itineraryApi, 
  validationApi,
  staticDataApi,
  agentApi 
} from './index';

// ==================== 1. 用户需求API测试 ====================

export async function testRequirementApi() {
  console.log('=== 测试用户需求API ===');
  
  try {
    // 提交需求
    const submitResponse = await requirementApi.submit({
      user_id: 'test_user_001',
      requirement: {
        city_name: '北京',
        travel_days: 3,
        total_budget: 5000,
        travel_type: 'family',
    
        preferences: ['历史古迹', '美食探索']
      }
    });
    
    console.log('✅ 需求提交成功:', submitResponse.data);
    const requirementId = submitResponse.data.requirement_id;
    
    // 解析需求
    const parseResponse = await requirementApi.parse(requirementId);
    console.log('✅ 需求解析成功:', parseResponse.data);
    
    // 获取需求详情
    const detailResponse = await requirementApi.getById(requirementId);
    console.log('✅ 获取需求详情:', detailResponse.data);
    
    return requirementId;
  } catch (error) {
    console.error('❌ 需求API测试失败:', error);
    throw error;
  }
}

// ==================== 2. 任务分解API测试 ====================

export async function testTaskApi(requirementId: string) {
  console.log('\n=== 测试任务分解API ===');
  
  try {
    // 任务分解
    const decomposeResponse = await taskApi.decompose(requirementId, {
      city_name: '北京',
      travel_days: 3,
      total_budget: 5000,
      travel_date: '2026-05-20',
      traveler_count: 2,
      preferences: ['历史古迹', '美食探索']
    });
    
    console.log('✅ 任务分解成功:', decomposeResponse.data);
    const taskId = decomposeResponse.data.task_id;
    
    // 查询任务状态
    const statusResponse = await taskApi.getById(taskId);
    console.log('✅ 任务状态:', statusResponse.data);
    
    return taskId;
  } catch (error) {
    console.error('❌ 任务API测试失败:', error);
    throw error;
  }
}

// ==================== 3. 行程管理API测试 ====================

export async function testItineraryApi() {
  console.log('\n=== 测试行程管理API ===');
  
  try {
    // 创建行程
    const createResponse = await itineraryApi.create({
      user_id: 'test_user_001',
      requirement_id: 'test_req_001',
      title: '北京三日游',
      city_name: '北京',
      travel_days: 3,
      total_budget: 5000,
      day_plans: [
        {
          day: 1,
          date: '2026-05-20',
          attractions: [
            {
              name: '故宫博物院',
              visit_time: '上午',
              visit_duration: '3小时',
              ticket_price: 60
            }
          ],
          meals: [
            {
              name: '全聚德烤鸭',
              meal_time: '中午',
              avg_price_per_person: 150
            }
          ]
        }
      ]
    });
    
    console.log('✅ 行程创建成功:', createResponse.data);
    const itineraryId = createResponse.data.itinerary_id;
    
    // 获取行程详情
    const detailResponse = await itineraryApi.getById(itineraryId);
    console.log('✅ 获取行程详情:', detailResponse.data);
    
    // 更新行程
    const updateResponse = await itineraryApi.update(itineraryId, {
      title: '北京三日游（修改版）'
    });
    console.log('✅ 行程更新成功:', updateResponse.data);
    
    // 获取用户所有行程
    const userResponse = await itineraryApi.getByUser('test_user_001');
    console.log('✅ 用户行程列表:', userResponse.data);
    
    // 删除行程
    const deleteResponse = await itineraryApi.delete(itineraryId);
    console.log('✅ 行程删除成功:', deleteResponse.data);
    
  } catch (error) {
    console.error('❌ 行程API测试失败:', error);
    throw error;
  }
}

// ==================== 4. 行程校验API测试 ====================

export async function testValidationApi() {
  console.log('\n=== 测试行程校验API ===');
  
  try {
    // 时间冲突检测
    const conflictResponse = await validationApi.checkTimeConflict({
      schedule: [
        {
          name: '故宫博物院',
          start_time: '09:00',
          end_time: '12:00',
          activity_type: 'attraction',
          location: '北京市东城区'
        },
        {
          name: '午餐',
          start_time: '11:30',
          duration: '1小时',
          activity_type: 'meal',
          location: '王府井'
        }
      ]
    });
    
    console.log('✅ 时间冲突检测结果:', conflictResponse.data);
    
    if (conflictResponse.data.has_conflict) {
      console.warn('⚠️ 发现时间冲突:', conflictResponse.data.conflicts);
    } else {
      console.log('✅ 无时间冲突');
    }
    
  } catch (error) {
    console.error('❌ 校验API测试失败:', error);
    throw error;
  }
}

// ==================== 5. 静态数据API测试 ====================

export async function testStaticDataApi() {
  console.log('\n=== 测试静态数据API ===');
  
  try {
    // 获取城市列表
    const citiesResponse = await staticDataApi.getCities();
    console.log('✅ 城市列表:', citiesResponse.data);
    
    // 获取北京的景点
    const attractionsResponse = await staticDataApi.getAttractionsByCity('北京');
    console.log('✅ 北京景点:', attractionsResponse.data);
    
    // 获取所有景点
    const allAttractions = await staticDataApi.getAttractions();
    console.log('✅ 所有景点:', allAttractions.data);
    
  } catch (error) {
    console.error('❌ 静态数据API测试失败:', error);
    throw error;
  }
}

// ==================== 6. 智能体API测试 ====================

export async function testAgentApi() {
  console.log('\n=== 测试智能体API ===');
  
  try {
    // 景点推荐
    const attractionsResponse = await agentApi.getAttractions({
      city_name: '西安',
      travel_days: 2,
      preferences: ['历史古迹'],
      ticket_budget: 500,
      traveler_count: 2
    });
    console.log('✅ 景点推荐:', attractionsResponse.data);
    
    // 住宿推荐
    const hotelsResponse = await agentApi.getHotels({
      city_name: '西安',
      check_in_date: '2026-08-01',
      check_out_date: '2026-08-03',
      nights: 2,
      budget_per_night: 300,
      traveler_count: 2
    });
    console.log('✅ 住宿推荐:', hotelsResponse.data);
    
    // 美食推荐
    const foodResponse = await agentApi.getFood({
      city_name: '西安',
      travel_days: 2,
      budget_per_person: 100,
      cuisine_preference: '本地特色',
      preferences: ['美食探索']
    });
    console.log('✅ 美食推荐:', foodResponse.data);
    
    // 交通推荐
    const transportResponse = await agentApi.getTransport({
      from_location: {
        name: '西安钟楼',
        lat: 34.261,
        lng: 108.942
      },
      to_location: {
        name: '西安兵马俑',
        lat: 34.384,
        lng: 109.273
      },
      mode_preference: 'transit'
    });
    console.log('✅ 交通推荐:', transportResponse.data);
    
  } catch (error) {
    console.error('❌ 智能体API测试失败:', error);
    throw error;
  }
}

// ==================== 完整流程测试 ====================

export async function testFullWorkflow() {
  console.log('\n🚀 开始完整流程测试\n');
  
  try {
    // 1. 提交需求
    // 3. 测试其他API
    await testItineraryApi();
    await testValidationApi();
    await testStaticDataApi();
    await testAgentApi();
    
    console.log('\n✅ 所有API测试完成！');
  } catch (error) {
    console.error('\n❌ 完整流程测试失败:', error);
  }
}

// 在浏览器控制台执行测试
// import { testFullWorkflow } from '@/services/apiTest';
// testFullWorkflow();
