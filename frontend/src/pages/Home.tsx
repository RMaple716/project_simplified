import { useNavigate } from 'react-router-dom';
import { Row, Col, Typography } from 'antd';
import QuickWeather from '../components/QuickWeather';

const { Title, Paragraph } = Typography;

const Home: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div style={{ padding: '40px 24px 60px', maxWidth: '1000px', margin: '0 auto' }}>
      {/* 【去AI味】标题：没有"欢迎"、"智能"等空洞词，用具体场景引发共鸣 */}
      <div style={{ marginBottom: 56, textAlign: 'center' }}>
        <Title
          style={{
            fontSize: '3.2rem',
            fontWeight: 600,
            letterSpacing: '-0.03em',
            lineHeight: 1.1,
            margin: '0 0 12px 0',
            fontFamily: "'Cormorant Garamond', Georgia, serif",
          }}
        >
          下一站，去哪？
        </Title>
        <Paragraph
          style={{
            fontSize: 16,
            color: '#8a7a70',
            maxWidth: 420,
            margin: '0 auto',
            lineHeight: 1.7,
          }}
        >
          把想法丢进来，我们替你理成一张老地图一样靠谱的行程。
        </Paragraph>
      </div>

      {/* 【去AI味】两个入口卡片：不对称布局 + 文字错位 */}
      <Row gutter={[32, 32]}>
        <Col xs={24} md={12}>
          {/* 【去AI味】左侧卡片：文字靠左对齐，而非居中；图片占位用纯色块 */}
          <div
            onClick={() => navigate('/requirement')}
            style={{
              cursor: 'pointer',
              border: '1px solid #e0d8ce',
              background: '#faf7f2',
              padding: 0,
              transition: 'all 0.25s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = '4px 6px 20px rgba(44,36,32,0.08)';
              e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = 'none';
              e.currentTarget.style.transform = 'none';
            }}
          >
            {/* 【去AI味】顶部色块模拟一张"照片"，留给人想象 */}
            <div
              style={{
                height: 120,
                background: '#d9cfc0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 32,
                letterSpacing: 4,
                color: '#8a7a70',
                fontWeight: 300,
              }}
            >
              · · ·
            </div>
            <div style={{ padding: '20px 24px 28px' }}>
              <Title level={3}
                style={{
                  margin: '0 0 6px 0',
                  fontFamily: "'Cormorant Garamond', Georgia, serif",
                  fontSize: '1.6rem',
                  letterSpacing: '-0.02em',
                }}
              >
                说走就走
              </Title>
              {/* 【去AI味】文案不使用"AI智能规划"等词汇，改用具体的体验描述 */}
              <Paragraph style={{ color: '#8a7a70', fontSize: 14, margin: 0, lineHeight: 1.7 }}>
                告诉我你想去哪、待几天、大概多少预算。
                剩下的路线、住处、馆子，我们来张罗。
              </Paragraph>
              <div style={{ marginTop: 16, fontSize: 13, color: '#5a4e48', letterSpacing: 0.5 }}>
                ——
              </div>
            </div>
          </div>
        </Col>

        <Col xs={24} md={12}>
          {/* 【去AI味】右侧卡片：与左侧不同的内边距，打破对称 */}
          <div
            onClick={() => navigate('/itineraries')}
            style={{
              cursor: 'pointer',
              border: '1px solid #e0d8ce',
              background: '#faf7f2',
              padding: 0,
              transition: 'all 0.25s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = '4px 6px 20px rgba(44,36,32,0.08)';
              e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = 'none';
              e.currentTarget.style.transform = 'none';
            }}
          >
            <div
              style={{
                height: 120,
                background: '#e6ddd0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 28,
                letterSpacing: 6,
                color: '#8a7a70',
              }}
            >
              ·&nbsp;·&nbsp;·
            </div>
            {/* 【去AI味】文字错位：左侧内边距比右侧大，打破完美居中 */}
            <div style={{ padding: '20px 28px 28px 24px' }}>
              <Title level={3}
                style={{
                  margin: '0 0 6px 0',
                  fontFamily: "'Cormorant Garamond', Georgia, serif",
                  fontSize: '1.6rem',
                  letterSpacing: '-0.02em',
                }}
              >
                回头看看
              </Title>
              <Paragraph style={{ color: '#8a7a70', fontSize: 14, margin: 0, lineHeight: 1.7 }}>
                以前攒下的路线都在这儿了。
                改一改、翻一翻，说不定能发现上次错过的店。
              </Paragraph>
              <div style={{ marginTop: 16, fontSize: 13, color: '#5a4e48', letterSpacing: 0.5 }}>
                ——
              </div>
            </div>
          </div>
        </Col>
      </Row>

            {/* 快捷天气查询 */}
      <QuickWeather />

      {/* 【去AI味】底部小字：不写提示，写一句有画面感的话 */}
      <div style={{ marginTop: 48, textAlign: 'center', color: '#b0a498', fontSize: 13, lineHeight: 1.8 }}>
        选一个方向，剩下的交给我们。
      </div>
    </div>
  );
};

export default Home;
