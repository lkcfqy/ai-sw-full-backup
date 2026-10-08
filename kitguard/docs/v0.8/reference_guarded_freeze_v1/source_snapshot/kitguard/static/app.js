/* KitGuard local workbench. No synthetic results or remote dependencies. */
'use strict';

const PARTS = ['bolt', 'nut', 'washer', 'bracket'];
const DEFAULT_REQUIREMENTS = { bolt: 2, nut: 2, washer: 2, bracket: 1 };
const STRINGS = {
  ko: {
    workspace: '키팅 검증', orders: '작업지시', newOrder: '새 작업지시', search: '작업지시 검색', emptyOrders: '첫 작업지시를 만들면\n이곳에서 진행 상태를 확인할 수 있습니다.', noSearch: '검색 결과가 없습니다.', local: '이 기기에서 실행', localNote: '사진과 기록은 로컬에 저장됩니다.', allOrders: '작업 워크스페이스', modelReady: '로컬 모델 준비', modelLoading: '모델 준비 중', modelUnavailable: '모델 확인 필요', disconnected: '서버 연결 없음', refresh: '새로고침', language: '언어', menu: '작업지시 목록', close: '닫기', cancel: '취소', save: '저장', loading: '워크스페이스를 불러오는 중', pending: '검증 대기', needs_action: '조치 필요', ready: '확인 준비', completed: '완료 기록됨', revision: '버전', created: '생성', updated: '업데이트', export: '기록 내보내기', revise: '작업지시 변경', references: '기준 부품', printTray: '번호 트레이 열기', welcomeEyebrow: 'LOCAL · EVIDENCE · VERIFICATION', welcomeTitle: '한 번의 확인보다,', welcomeAccent: '올바른 다음 행동.', welcomeBody: '사진과 주문을 대조하고, 주문이 바뀌면 근거를 다시 확인합니다. 출처가 있는 공개 사진으로 시작하거나 보유한 사진을 등록해 판단과 이력을 남기세요.', welcomeCreate: '첫 작업지시 만들기', welcomeNote1: '4종 부품 · 최대 12개', welcomeNote2: '검토 의견과 버전을 함께 보존', welcomeVisual: 'YOUR VERIFICATION WORKSPACE', welcomeCaption: '시작 전 안내 이미지 · 실제 검증 결과가 아닙니다.', stepOrder: '작업지시', stepEvidence: '사진 검사', stepRecord: '결과 기록', headingEyebrow: 'KITTING WORKSPACE', partsCount: '{count}종', totalCount: '총 {count}개', currentRevision: '현재 요구사항 R{revision}', evidence: '사진 증거', camera: '카메라', upload: '사진 올리기', replacePhoto: '새 사진', emptyPhotoTitle: '확인할 실물을 보여주세요', emptyPhotoBody: '부품을 밝은 곳에 놓고 전체 트레이를 촬영하세요. 번호가 보이고 부품이 겹치지 않으면 확인이 쉬워집니다.', emptyPhotoFormats: 'JPG, PNG, WEBP · 최대 12 MB', dropPhoto: '여기에 사진을 놓으세요', original: '실물 사진', focusRegion: '추가 확인 영역', noPhoto: '사진이 아직 없습니다', photoVersion: '사진 버전 R{revision}', currentPhoto: '최신 사진', historicalPhoto: '이전 사진', historicalTitle: '이전 증거를 보고 있습니다', historicalMessage: '수량 대조와 완료 확인은 현재 버전의 최신 사진에서 진행하세요.', showLatest: '최신 사진으로 돌아가기', photoHistory: '증거 사진 이력', captureHint: '사진 이후 부품을 옮겼다면 새로 촬영하세요. 이미지 기록은 물체의 신원이나 촬영 시점 자체를 보증하지 않습니다.', inspect: '실물 검증 실행', inspecting: '로컬 모델이 사진을 확인하고 있습니다', inspectingNote: '실제 추론 응답을 기다립니다. 최초 실행 시 모델을 불러와 시간이 더 걸릴 수 있습니다.', elapsed: '{seconds}초 경과', inspectPrompt: 'AI 관찰 + 수량·버전 검사', inspectSupport: '최신 사진과 현재 작업지시를 대조합니다.', inspectOldPhoto: '현재 버전의 최신 사진을 선택하세요.', inspectMissingPhoto: '사진을 올리면 검증을 시작할 수 있습니다.', inspectMissingRefs: '정확한 비교를 위해 네 종류의 기준 사진을 등록하세요.', checkTitle: '부품 대조', part: '부품', required: '필요', observed: '관찰', result: '차이', totalRequired: '필요 수량', referencesCount: '{count}/4 등록', manageReferences: '기준 부품 관리', nextAction: 'NEXT ACTION', waitingTitle: '증거를 기다리고 있습니다', waitingMessage: '사진을 올리고 실물 검증을 실행하면, 다음 확인 행동을 안내합니다.', needsInspectTitle: '새 증거를 확인할 차례입니다', needsInspectMessage: '현재 사진을 검증하여 수량과 작업지시 버전을 확인하세요.', staleTitle: '이전 확인은 유효하지 않습니다', staleMessage: '사진, 기준 부품 또는 작업지시가 변경되었습니다. 현재 조건으로 다시 검증하세요.', recaptureTitle: '조금 더 명확한 증거가 필요합니다', correctTitle: '부품 구성을 바로잡아 주세요', manualTitle: '사람의 확인이 필요합니다', manualMessage: '현재 증거만으로 결과를 확정할 수 없습니다. 부품과 주문을 직접 확인하고 새로운 증거를 올려주세요.', readyTitle: '최종 확인을 진행하세요', readyMessage: '관찰한 수량이 현재 요구사항과 일치합니다. 실제 부품을 직접 확인한 뒤 완료를 기록하세요.', completedTitle: '확인 결과가 기록되었습니다', completedMessage: '현재 버전의 작업지시와 증거가 연결되어 저장되었습니다. 아래 이력에서 기록을 확인할 수 있습니다.', complete: '확인 후 완료 기록', completionFootnote: '실험용 소프트웨어 기록입니다. 생산설비 제어 또는 자동 출하와 연결되지 않습니다.', followup: '새 증거 촬영', noAction: '추가 행동 없음', issues: '확인 사항', model: '모델', latency: '추론 {seconds}초', invalidCheck: '효력 없음', validCheck: '현재 버전 확인', testWarning: '테스트 관찰 결과입니다. 실제 모델 검증으로 사용할 수 없습니다.', protocolTitle: '확인 범위', protocolText: '종류별 알려진 기준 부품만 확인합니다. 크기, 나사산, 재질은 사진으로 인증하지 않습니다. 불명확한 물체는 추측하여 완료하지 않습니다.', protocol1: '4종 · 종류별 0–3개', protocol2: '보완 요청 최대 2회', protocol3: '사람이 실물 이동', history: '작업 이력', emptyHistory: '작업이 진행되면 주문 변경, 사진과 확인 결과가 기록됩니다.', footerLocal: 'LOCAL WORKSPACE', footerNote: '관찰의 한계를 유지하며, 실행 결과를 확인합니다.', createTitle: '새 작업지시 만들기', createDescription: '부품별 필요한 수량을 지정하세요. 첫 검증은 실제 사진을 올린 뒤 시작됩니다.', orderTitle: '작업지시 이름', orderPlaceholder: '예: 조립 키트 · A01', defaultOrderTitle: '조립 키트', quantityLabel: '필요한 부품', quantityLimit: '종류별 0–3개 · 합계 1–12개', createAction: '작업지시 만들기', defaultNote: '기본 수량은 편집할 수 있습니다. 검증 결과는 미리 생성하지 않습니다.', reviseTitle: '작업지시 변경', reviseDescription: '변경을 승인하면 이전 확인 결과가 무효화됩니다.', structuredTab: '수량 직접 편집', naturalTab: '자연어 변경 제안', revisionReason: '변경 메모', revisionPlaceholder: '변경 이유 또는 지시를 입력하세요.', naturalLabel: '어떻게 바꿀까요?', naturalPlaceholder: '예: 와셔를 3개로 변경하고 나머지는 유지해 주세요.', propose: '변경안 검토', proposing: '변경안을 해석하고 있습니다', proposalTitle: '아직 적용되지 않은 변경안', proposalReview: '아래 차이를 확인한 후 승인해야 적용됩니다.', approveRevision: '확인하고 R{revision} 적용', directRevisionNote: '저장 시 현재 버전을 다시 확인하고 이전 결과를 무효화합니다.', noChanges: '현재 요구사항과 수량이 같습니다.', proposalStale: '작업지시가 변경되어 이 제안을 적용할 수 없습니다. 다시 제안해 주세요.', referenceTitle: '기준 부품 사진', referenceDescription: '각 종류의 알려진 기준 부품 한 개를 선명하게 촬영하세요. 크기·재질 인증을 대신하지 않습니다.', referenceNote: '기준 사진을 교체하면 이전 검증 결과가 무효화됩니다.', register: '등록', change: '교체', referenceUploaded: '기준 사진이 저장되었습니다.', cameraTitle: '실물 촬영', cameraDescription: '트레이 전체와 부품이 선명하게 보이도록 배치하세요.', cameraStarting: '카메라를 여는 중입니다.', cameraNote: '이 미리보기는 저장되지 않습니다. 촬영 버튼을 누르면 현재 프레임만 로컬 작업지시에 업로드됩니다.', capture: '촬영하고 업로드', cameraFailed: '카메라를 열 수 없습니다. 브라우저 권한을 확인하거나 사진 업로드를 이용하세요.', completeTitle: '실물 확인 후 기록', completeDescription: 'AI의 관찰은 실물의 절대적인 정확성을 보증하지 않습니다.', confirmLabel: '현재 주문과 실제 부품을 직접 확인했고, 촬영 후 구성 변경이 없음을 확인합니다.', confirmVersion: '현재 버전 R{revision}의 검증 결과를 저장합니다.', confirmSubmit: '완료 기록 저장', modelTitle: '로컬 모델 상태', modelDescription: '모델 상태는 서버의 실제 응답을 표시합니다.', modelAvailable: '파일 사용 가능', modelLoaded: '메모리 로드', yes: '예', no: '아니요', modelPath: '모델 경로', modelName: '모델 이름', modelNotReady: '모델을 준비한 뒤 새로고침하세요. 파일이 준비되어 있으면 첫 검증 시 모델을 불러옵니다.', modelUnknown: '확인 중', orderCreated: '작업지시가 생성되었습니다.', revisionSaved: '새 버전이 적용되었습니다. 다시 확인해 주세요.', photoUploaded: '사진이 저장되었습니다. 실물 검증을 실행하세요.', checkFinished: '검증 응답이 도착했습니다.', completedSaved: '완료 기록을 저장하고 다시 확인했습니다.', requestFailed: '요청을 처리하지 못했습니다.', connectionFailed: '로컬 서버에 연결할 수 없습니다. 서버 실행 상태를 확인하고 새로고침하세요.', staleError: '작업지시가 다른 곳에서 변경되었습니다. 최신 상태를 불러왔습니다. 열린 입력창을 닫고 다시 확인한 뒤 시도하세요.', unavailableError: '로컬 모델을 사용할 수 없습니다. 모델 상태를 확인하세요.', invalidTitle: '작업지시 이름을 입력하세요.', invalidCounts: '각 수량은 0–3의 정수이며 합계는 1–12여야 합니다.', invalidInstruction: '변경 지시를 입력하세요.', invalidPhoto: 'JPG, PNG, WEBP 사진을 선택하세요. 최대 크기는 12 MB입니다.', noOrder: '먼저 작업지시를 선택하세요.', uploading: '사진을 저장하는 중', working: '처리 중', unknown: '확인 필요', match: '일치', unavailable: '미확인', seconds: '초', tray: '12칸 번호 트레이', serverReload: '다시 연결', confirmationRequired: '실물 확인 항목에 체크해 주세요.', noCurrentCheck: '현재 버전의 유효한 검증이 필요합니다.', referencesSavedNote: '등록한 사진은 이 작업지시에 연결됩니다.', orderNotFound: '이 작업지시를 불러올 수 없습니다.', busyWait: '현재 작업이 끝난 뒤 다시 시도하세요.'
  },
  zh: {
    workspace: '备料核验', orders: '工单', newOrder: '新建工单', search: '搜索工单', emptyOrders: '创建第一份工单后，\n可在这里查看进度。', noSearch: '没有匹配的工单。', local: '在此设备运行', localNote: '照片与记录保存在本地。', allOrders: '核验工作台', modelReady: '本地模型就绪', modelLoading: '模型准备中', modelUnavailable: '需要检查模型', disconnected: '服务器未连接', refresh: '刷新', language: '语言', menu: '工单列表', close: '关闭', cancel: '取消', save: '保存', loading: '正在加载工作台', pending: '待核验', needs_action: '需要处理', ready: '待人工确认', completed: '已记录完成', revision: '版本', created: '创建于', updated: '更新于', export: '导出记录', revise: '修改工单', references: '参考零件', printTray: '打开编号托盘', welcomeEyebrow: 'LOCAL · EVIDENCE · VERIFICATION', welcomeTitle: '每一次核验，', welcomeAccent: '都有下一步依据。', welcomeBody: '核对照片与订单；订单变更时重新确认依据。可以从有来源的公开照片开始，也可以登记自己的照片，保存判断与版本记录。', welcomeCreate: '创建第一份工单', welcomeNote1: '4 类零件 · 最多 12 件', welcomeNote2: '由人最终确认', welcomeVisual: 'YOUR VERIFICATION WORKSPACE', welcomeCaption: '使用前示意图 · 不是实际核验结果。', stepOrder: '工单要求', stepEvidence: '实物核验', stepRecord: '结果记录', headingEyebrow: 'KITTING WORKSPACE', partsCount: '{count} 类', totalCount: '共 {count} 件', currentRevision: '当前要求 R{revision}', evidence: '照片证据', camera: '相机', upload: '上传照片', replacePhoto: '新照片', emptyPhotoTitle: '让实物成为核验依据', emptyPhotoBody: '在明亮环境拍摄整个托盘。让编号清楚可见、零件互不重叠，有助于可靠核验。', emptyPhotoFormats: 'JPG、PNG、WEBP · 最大 12 MB', dropPhoto: '将照片拖到这里', original: '待检照片', focusRegion: '需要补充证据的区域', noPhoto: '尚未上传照片', photoVersion: '照片版本 R{revision}', currentPhoto: '最新照片', historicalPhoto: '历史照片', historicalTitle: '正在查看历史证据', historicalMessage: '请返回当前版本的最新照片，再进行数量比对或完成确认。', showLatest: '返回最新照片', photoHistory: '照片证据历史', captureHint: '拍照后如果移动了零件，请重新拍摄。图片记录本身不能证明物件身份或真实拍摄时间。', inspect: '运行实物核验', inspecting: '本地模型正在核验照片', inspectingNote: '正在等待实际推理结果。首次运行需要加载模型，可能用时更长。', elapsed: '已等待 {seconds} 秒', inspectPrompt: 'AI 观察 + 数量、版本校验', inspectSupport: '将最新照片与当前工单进行比对。', inspectOldPhoto: '请选择当前版本的最新照片。', inspectMissingPhoto: '上传照片后即可开始核验。', inspectMissingRefs: '请登记四类参考照片，以便准确比对。', checkTitle: '零件比对', part: '零件', required: '需求', observed: '观察', result: '差异', totalRequired: '需求总量', referencesCount: '已登记 {count}/4', manageReferences: '管理参考零件', nextAction: 'NEXT ACTION', waitingTitle: '等待实物证据', waitingMessage: '上传照片并运行实物核验，即可获取下一步操作建议。', needsInspectTitle: '现在可以核验新证据', needsInspectMessage: '运行核验，确认当前照片中的数量和订单版本。', staleTitle: '先前核验已经失效', staleMessage: '照片、参考零件或工单已发生变化。请按当前条件重新核验。', recaptureTitle: '需要更清楚的证据', correctTitle: '请调整零件配置', manualTitle: '需要人工核验', manualMessage: '当前证据不足以得出结论。请直接检查零件与订单，并上传新的证据。', readyTitle: '请进行最后一次人工确认', readyMessage: '观察数量与当前要求一致。请直接核对实物后，再记录完成。', completedTitle: '核验结果已记录', completedMessage: '当前工单版本已与证据关联保存。可在下方历史中查看记录。', complete: '确认并记录完成', completionFootnote: '这是实验工单的软件记录，不连接生产设备控制或自动出库。', followup: '拍摄新证据', noAction: '无需追加操作', issues: '核验说明', model: '模型', latency: '推理 {seconds} 秒', invalidCheck: '已失效', validCheck: '当前版本核验', testWarning: '这是测试观察结果，不能作为真实模型核验使用。', protocolTitle: '核验范围', protocolText: '仅核验每类已知参考零件。照片不能认证尺寸、螺纹或材质；看不清的物件不会依靠猜测完成工单。', protocol1: '4 类 · 每类 0–3 件', protocol2: '最多 2 轮补证', protocol3: '由人移动实物', history: '操作历史', emptyHistory: '工单变更、照片和核验结果会记录在这里。', footerLocal: 'LOCAL WORKSPACE', footerNote: '保留观察的不确定性，核对实际执行结果。', createTitle: '创建新工单', createDescription: '指定各类零件的需求数量。上传真实照片后开始第一次核验。', orderTitle: '工单名称', orderPlaceholder: '例如：装配套件 · A01', defaultOrderTitle: '装配套件', quantityLabel: '所需零件', quantityLimit: '每类 0–3 件 · 总计 1–12 件', createAction: '创建工单', defaultNote: '默认数量可以修改，不会预先生成核验结果。', reviseTitle: '修改工单', reviseDescription: '批准变更后，先前的核验结果将失效。', structuredTab: '直接修改数量', naturalTab: '自然语言变更', revisionReason: '变更说明', revisionPlaceholder: '输入变更原因或指令。', naturalLabel: '需要怎样修改？', naturalPlaceholder: '例如：将垫圈改为 3 件，其余保持不变。', propose: '生成变更提案', proposing: '正在解析变更指令', proposalTitle: '待批准的变更提案', proposalReview: '核对以下差异，确认批准后才会生效。', approveRevision: '确认并应用 R{revision}', directRevisionNote: '保存时重新核对当前版本，并使旧核验结果失效。', noChanges: '数量与当前要求相同。', proposalStale: '工单已改变，此提案无法应用。请重新生成。', referenceTitle: '参考零件照片', referenceDescription: '为每类已知参考零件拍摄一张清晰单件照片。这不能代替尺寸或材质认证。', referenceNote: '替换参考照片会使先前的核验结果失效。', register: '登记', change: '替换', referenceUploaded: '参考照片已保存。', cameraTitle: '拍摄实物', cameraDescription: '请让整个托盘与零件清楚入镜。', cameraStarting: '正在打开相机。', cameraNote: '预览不会被保存。点击拍摄后，仅将当前画面上传到本地工单。', capture: '拍摄并上传', cameraFailed: '无法打开相机。请检查浏览器权限，或使用照片上传。', completeTitle: '核对实物后记录', completeDescription: 'AI 的观察不能保证实物绝对正确。', confirmLabel: '我已对照当前工单检查实际零件，并确认拍照后未改变配置。', confirmVersion: '将保存当前 R{revision} 版本的核验结果。', confirmSubmit: '保存完成记录', modelTitle: '本地模型状态', modelDescription: '以下状态来自服务器的实际响应。', modelAvailable: '文件可用', modelLoaded: '已加载至内存', yes: '是', no: '否', modelPath: '模型路径', modelName: '模型名称', modelNotReady: '准备好模型后请刷新。模型文件可用时，首次核验将进行加载。', modelUnknown: '检查中', orderCreated: '工单已创建。', revisionSaved: '新版本已应用，请重新核验。', photoUploaded: '照片已保存，请运行实物核验。', checkFinished: '已收到核验结果。', completedSaved: '完成记录已保存，并已回读确认。', requestFailed: '无法完成请求。', connectionFailed: '无法连接本地服务器。请确认服务已启动并刷新。', staleError: '工单已在别处发生变化。已加载最新状态，请关闭当前输入窗口，重新核对后再试。', unavailableError: '本地模型暂不可用，请检查模型状态。', invalidTitle: '请输入工单名称。', invalidCounts: '各数量须为 0–3 的整数，合计须为 1–12。', invalidInstruction: '请输入变更指令。', invalidPhoto: '请选择 JPG、PNG 或 WEBP 图片，最大 12 MB。', noOrder: '请先选择工单。', uploading: '正在保存照片', working: '处理中', unknown: '需要核实', match: '一致', unavailable: '未确认', seconds: '秒', tray: '12 格编号托盘', serverReload: '重新连接', confirmationRequired: '请勾选实物确认项。', noCurrentCheck: '需要当前版本的有效核验。', referencesSavedNote: '参考照片将关联到此工单。', orderNotFound: '无法加载此工单。', busyWait: '请等待当前操作完成后重试。'
  }
};

const ICON_PATHS = {
  logo: '<path d="M5 3v18m1-9L18 3M6 12l12 9"/><circle cx="19" cy="12" r="2" fill="currentColor" stroke="none"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4 4"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  camera: '<path d="M8 6 9.5 3h5L16 6h4a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1z"/><circle cx="12" cy="12.5" r="3.5"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v4h16v-4"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  shield: '<path d="m12 3 8 3v5c0 5-4 8-8 10-4-2-8-5-8-10V6z"/><path d="m8 12 3 3 5-6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  edit: '<path d="m14 5 5 5M4 20l5-1L21 7l-5-5L4 14z"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  scan: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m8 0h5v-5M3 12h18"/>',
  refresh: '<path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  alert: '<path d="m12 3 10 18H2zM12 9v5M12 17h.01"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 3v3m6-3v3M9 18v3m6-3v3M3 9h3m-3 6h3m12-6h3m-3 6h3"/><rect x="9" y="9" width="6" height="6" rx="1"/>',
  file: '<path d="M14 3H5v18h14V8zM14 3v5h5M8 13h8m-8 4h5"/>',
  bolt: '<path d="m9 3 6 0 3 4-3 4H9L6 7zM10 11v9h4v-9M9 14h6m-6 3h6"/>',
  nut: '<path d="m7 4 10 0 5 8-5 8H7l-5-8z"/><circle cx="12" cy="12" r="3.3"/>',
  washer: '<ellipse cx="12" cy="12" rx="10" ry="8"/><ellipse cx="12" cy="12" rx="4.2" ry="3.2"/>',
  bracket: '<path d="M4 4h5v11h11v5H4z"/><circle cx="6.5" cy="8" r=".8"/><circle cx="15" cy="17.5" r=".8"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  branch: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/><path d="M6 7v10m0-5h6a6 6 0 0 0 6-3"/>',
  hand: '<path d="M8 12V5a2 2 0 0 1 4 0v6-8a2 2 0 0 1 4 0v9-6a2 2 0 0 1 4 0v9c0 4-3 6-7 6-3 0-5-1-7-4l-3-4a2 2 0 0 1 3-2l2 2"/>'
};

function icon(name, className = '') {
  return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name] || ICON_PATHS.file}</svg>`;
}
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function storedLanguage() { try { return localStorage.getItem('kitguard-language') === 'zh' ? 'zh' : 'ko'; } catch { return 'ko'; } }
const state = { lang: storedLanguage(), orders: [], order: null, health: null, selectedPhoto: null, search: '', busy: null, error: null, initialized: false, sidebarOpen: false, proposal: null, revisionMode: 'structured', stream: null, referencePart: null, completionKeys: new Map(), startedAt: 0, elapsedTimer: null, toastTimer: null, loadToken: 0 };
function t(key, values = {}) { let value = (typeof publicOrderText === 'function' && publicOrderText(key)) || STRINGS[state.lang][key] || STRINGS.ko[key] || key; for (const [k, v] of Object.entries(values)) value = value.replaceAll(`{${k}}`, String(v)); return value; }
function partLabel(part) { return ({ ko: { bolt: '나사류', nut: '너트', washer: '와셔', bracket: '브래킷' }, zh: { bolt: '螺纹件', nut: '螺母', washer: '垫圈', bracket: '角码' } })[state.lang][part] || part; }
function total(requirements) { return PARTS.reduce((n, p) => n + (Number(requirements?.[p]) || 0), 0); }
function formatDate(value, mode = 'short') { if (!value) return '—'; const date = new Date(value); if (Number.isNaN(date.getTime())) return String(value); return new Intl.DateTimeFormat(state.lang === 'zh' ? 'zh-CN' : 'ko-KR', mode === 'time' ? { hour: '2-digit', minute: '2-digit', hour12: false } : { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date); }
function photos(order = state.order) { return [...(order?.photos || [])].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()); }
function latestPhoto(order = state.order) { return photos(order).at(-1) || null; }
function selectedPhoto() { return photos().find(p => String(p.id) === String(state.selectedPhoto)) || latestPhoto(); }
function currentCheck() { if (state.busy === 'inspect') return null; const c = state.order?.latest_check; return c && c.valid && c.revision === state.order.revision && c.photo_id === latestPhoto()?.id && c.photo_id === selectedPhoto()?.id ? c : null; }
function statusLabel(status) { return t(['pending', 'needs_action', 'ready', 'completed', 'manual_reviewed'].includes(status) ? status : 'pending'); }
function orderStatusLabel(order) { return order?.demo_source && order.status === 'ready' ? prText('digitalReady') : statusLabel(order.status); }
function statusBadge(status) { return `<span class="badge ${esc(status)}"><span class="dot ${esc(status)}"></span>${esc(statusLabel(status))}</span>`; }
function imageUrl(photo) { if (!photo) return ''; if (typeof photo === 'string') return photo.startsWith('/') ? photo : ''; return photo.url || (photo.id ? `/api/photos/${encodeURIComponent(photo.id)}` : ''); }
function apiErrorText(body) { const detail = body?.detail; if (typeof detail === 'string') return detail; if (Array.isArray(detail)) return detail.map(item => `${(item.loc || []).slice(1).join('.')}: ${item.msg || ''}`).join('\n'); return t('requestFailed'); }
async function api(path, options = {}) {
  let response;
  try { response = await fetch(path, { ...options, headers: { ...(options.body instanceof FormData ? {} : options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } }); }
  catch { const e = new Error(t('connectionFailed')); e.status = 0; throw e; }
  const contentType = response.headers.get('content-type') || '';
  const body = contentType.includes('json') ? await response.json() : null;
  if (!response.ok) { const e = new Error(apiErrorText(body)); e.status = response.status; throw e; }
  return body;
}
function post(path, body) { return api(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body) }); }
function toast(message) { const el = document.getElementById('toast'); el.textContent = message; el.classList.add('visible'); clearTimeout(state.toastTimer); state.toastTimer = setTimeout(() => el.classList.remove('visible'), 4600); }
function setBusy(kind) { state.busy = kind; state.startedAt = Date.now(); clearInterval(state.elapsedTimer); if (kind === 'inspect') state.elapsedTimer = setInterval(() => { const el = document.getElementById('elapsed'); if (el) el.textContent = t('elapsed', { seconds: Math.floor((Date.now() - state.startedAt) / 1000) }); }, 1000); render(); document.querySelectorAll('dialog[open] button[data-mutate]').forEach(b => { b.disabled = !!kind; }); }
function clearBusy() { state.busy = null; clearInterval(state.elapsedTimer); render(); document.querySelectorAll('dialog[open] button[data-mutate]').forEach(b => { b.disabled = false; }); }
function showError(error, dialogId) {
  const contextual = error.status === 409 ? t('staleError') : error.status === 503 ? t('unavailableError') : '';
  const message = contextual ? `${contextual}\n${error.message}` : error.message;
  state.error = message;
  if (dialogId) { const target = document.querySelector(`#${dialogId} .modal-error`); if (target) { target.textContent = message; target.classList.add('visible'); } }
  render();
}
async function refreshOrders() { const data = await api('/api/orders'); state.orders = data.orders || []; }
async function loadOrder(id) {
  const token = ++state.loadToken;
  try { const data = await api(`/api/orders/${encodeURIComponent(id)}`); if (token !== state.loadToken) return; state.order = data.order; state.historyView = null; state.selectedPhoto = latestPhoto()?.id || null; state.error = null; state.sidebarOpen = false; render(); if (typeof recoverInspectionState === 'function') await recoverInspectionState(); }
  catch (error) { if (token === state.loadToken) showError(error); }
}
async function refreshCurrent() { if (!state.order) return; const id = state.order.id; const data = await api(`/api/orders/${encodeURIComponent(id)}`); if (state.order?.id === id) state.order = data.order; }
async function refreshHealth() { try { state.health = await api('/api/health'); } catch { state.health = { ok: false, model: { available: false } }; } }
async function mutate(kind, work, successMessage, dialogId) {
  if (state.busy) { toast(t('busyWait')); return null; }
  state.error = null;
  setBusy(kind);
  try {
    const result = await work();
    if (result?.order) { state.order = result.order; if (result.photo) state.selectedPhoto = result.photo.id; }
    try { await refreshOrders(); } catch { /* A successful mutation remains successful if only list refresh failed. */ }
    if (successMessage) toast(t(successMessage));
    return result;
  } catch (error) {
    // Inference failures can change server state too; never retain old readiness after a failed request.
    try { await refreshCurrent(); await refreshOrders(); } catch { /* Preserve the original request error. */ }
    if (error.status === 503) await refreshHealth();
    showError(error, dialogId);
    return null;
  } finally { clearBusy(); }
}

function trayIllustration() {
  const cells = Array.from({ length: 12 }, (_, i) => { const x = 18 + (i % 4) * 54; const y = 18 + Math.floor(i / 4) * 49; return `<rect x="${x}" y="${y}" width="48" height="43" rx="6" fill="#fbfdf8" stroke="#dae4d3"/><text x="${x + 6}" y="${y + 11}" font-size="5" fill="#a1b197" font-family="monospace">${String(i + 1).padStart(2, '0')}</text>`; }).join('');
  return `<svg class="tray-illustration" viewBox="0 0 246 183" fill="none" aria-hidden="true"><rect x="4" y="6" width="238" height="171" rx="15" fill="#d9e3d0"/><rect x="3" y="3" width="238" height="171" rx="15" fill="#f5f8ee" stroke="#c7d4bf"/>${cells}<path d="M35 41h14M39 33h6v18h-6zm-4-1h14v5H35" fill="#b0beb3" stroke="#758b7f" stroke-width="1.1"/><path d="m94 32 10 0 5 8-5 8H94l-5-8z" fill="#b7c5b9" stroke="#809585"/><circle cx="99" cy="40" r="3.5" fill="#fafcf5" stroke="#809585"/><ellipse cx="153" cy="41" rx="10" ry="8" fill="#b8c7b9" stroke="#78917e"/><ellipse cx="153" cy="41" rx="4" ry="3.1" fill="#fbfdf8" stroke="#78917e"/><path d="M198 31h6v13h13v6h-19z" fill="#acbfae" stroke="#78907b"/><path d="M190 91h25m-12-12v25" stroke="#c7d8bf" stroke-width="1" stroke-dasharray="2 3"/><rect x="17" y="115" width="211" height="42" rx="7" stroke="#b6cbb0" stroke-dasharray="3 4" fill="none"/><path d="M227 2h12v12M3 159v12h12" stroke="#8dac80" stroke-width="2"/></svg>`;
}
function renderOrderList() {
  const container = document.getElementById('order-list'); if (!container) return;
  const items = state.orders.filter(o => `${o.title} ${o.id}`.toLowerCase().includes(state.search.toLowerCase()));
  container.innerHTML = items.length ? items.map(o => `<button class="order-item ${state.order?.id === o.id ? 'active' : ''}" data-action="select-order" data-id="${esc(o.id)}" ${state.busy ? 'disabled' : ''} ${state.order?.id === o.id ? 'aria-current="true"' : ''}><span class="order-item-title"><span class="dot ${esc(o.status)}"></span><span>${esc(o.title)}</span></span><span class="order-item-meta"><span>R${esc(o.revision)}</span><span>·</span><span>${esc(orderStatusLabel(o))}</span></span></button>`).join('') : `<p class="side-empty">${esc(state.search ? t('noSearch') : t('emptyOrders')).replaceAll('\n', '<br>')}</p>`;
}
function renderSidebar() { return `<aside class="sidebar ${state.sidebarOpen ? 'open' : ''}" aria-label="${esc(t('orders'))}"><a class="brand" href="/" aria-label="KitGuard"><span class="brand-symbol">${icon('logo')}</span><span><span class="brand-word">Kit<em>Guard</em></span><small>VERIFY WITH EVIDENCE</small></span></a><div class="sidebar-body"><button class="btn btn-primary btn-full sidebar-add" data-action="new-order" ${state.busy ? 'disabled' : ''}>${icon('plus')}${esc(t('newOrder'))}</button><div class="sidebar-heading"><span>${esc(t('orders'))}</span><span class="count-pill">${state.orders.length}</span></div><div class="sidebar-search">${icon('search')}<input id="order-search" type="search" autocomplete="off" placeholder="${esc(t('search'))}" aria-label="${esc(t('search'))}" value="${esc(state.search)}"></div><nav id="order-list" class="order-list"></nav></div><div class="sidebar-footer"><a href="/static/demo.html">${state.lang === 'zh' ? '公开照片审查 ↗' : '공개 사진 검토 ↗'}</a><a href="/static/trials.html">${state.lang === 'zh' ? '完整任务试用 ↗' : '전체 작업 시험 ↗'}</a><a href="/static/readiness.html">${state.lang === 'zh' ? '演示前检查 ↗' : '시연 준비 확인 ↗'}</a><a href="/static/study.html">${state.lang === 'zh' ? '固定照片验证 ↗' : '고정 사진 검증 ↗'}</a><a href="/static/detector.html">${state.lang === 'zh' ? '零件检测验证 ↗' : '부품 검출 확인 ↗'}</a><div class="local-badge">${icon('lock')}${esc(t('local'))}</div><p>${esc(t('localNote'))}</p></div></aside>${state.sidebarOpen ? '<button class="sidebar-backdrop" data-action="close-sidebar" aria-label="Close navigation"></button>' : ''}`; }
function renderTopbar() {
  const model = state.health?.model; const connected = state.health?.ok;
  const label = !connected && state.health ? 'disconnected' : model?.available ? 'modelReady' : state.health ? 'modelUnavailable' : 'modelUnknown';
  return `<header class="topbar"><div class="breadcrumb"><button class="mobile-menu icon-btn" data-action="toggle-sidebar" aria-label="${esc(t('menu'))}" aria-expanded="${state.sidebarOpen}">${icon('menu')}</button><span>${esc(t('allOrders'))}</span>${icon('chevron')}<strong>${esc(t('workspace'))}</strong></div><div class="topbar-actions"><button class="icon-btn" data-action="refresh-workspace" aria-label="${esc(t('refresh'))}" title="${esc(t('refresh'))}" ${state.busy ? 'disabled' : ''}>${icon('refresh')}</button><button class="model-state" data-action="model" title="${esc(t(label))}"><span class="dot ${model?.available ? 'ready' : state.health ? 'offline' : ''}"></span><span class="model-status-label">${esc(t(label))}</span></button><div class="language-toggle" aria-label="${esc(t('language'))}"><button data-action="language" data-lang="ko" class="${state.lang === 'ko' ? 'active' : ''}" aria-pressed="${state.lang === 'ko'}">한국어</button><button data-action="language" data-lang="zh" class="${state.lang === 'zh' ? 'active' : ''}" aria-pressed="${state.lang === 'zh'}">中文</button></div></div></header>`;
}
function renderWelcome() { return `<section class="welcome"><div class="welcome-copy"><p class="eyebrow">${esc(t('welcomeEyebrow'))}</p><h1>${esc(t('welcomeTitle'))}<span>${esc(t('welcomeAccent'))}</span></h1><p>${esc(t('welcomeBody'))}</p><div class="welcome-actions"><a class="btn btn-primary" href="/static/demo.html">${icon('image')}${esc(prText('publicStart'))}</a><button class="btn btn-secondary" data-action="new-order">${icon('plus')}${esc(t('welcomeCreate'))}</button><a class="btn btn-quiet" href="/api/templates/tray.svg" target="_blank" rel="noopener">${icon('grid')}${esc(t('printTray'))}</a></div><div class="welcome-notes"><span>${icon('grid')}${esc(t('welcomeNote1'))}</span><span>${icon('shield')}${esc(t('welcomeNote2'))}</span></div></div><div class="welcome-visual"><div class="welcome-visual-label"><span>${esc(t('welcomeVisual'))}</span>${icon('scan')}</div>${trayIllustration()}<div class="process-steps"><div class="process-step"><b>01</b><span>${esc(t('stepOrder'))}</span></div><div class="process-step"><b>02</b><span>${esc(t('stepEvidence'))}</span></div><div class="process-step"><b>03</b><span>${esc(t('stepRecord'))}</span></div></div><p class="welcome-caption">${esc(t('welcomeCaption'))}</p></div></section>`; }
function renderHeader(order) { return `<div class="workspace-heading"><div><p class="eyebrow">${esc(t('headingEyebrow'))}</p><div class="heading-title"><h1>${esc(order.title)}</h1>${order.demo_source && order.status === 'ready' ? `<span class="badge ready">${esc(prText('digitalReady'))}</span>` : statusBadge(order.status)}</div><div class="heading-subtitle"><span class="badge revision">R${esc(order.revision)}</span><span>${esc(t('partsCount', { count: PARTS.filter(p => order.requirements[p] > 0).length }))} · ${esc(t('totalCount', { count: total(order.requirements) }))}</span><span class="separator">/</span><span>${esc(t('updated'))} ${esc(formatDate(order.updated_at))}</span></div></div><div class="heading-buttons"><button class="btn btn-secondary" data-action="revise" ${state.busy ? 'disabled' : ''}>${icon('edit')}${esc(t('revise'))}</button><a class="btn btn-secondary" href="/api/orders/${encodeURIComponent(order.id)}/export" download>${icon('download')}${esc(t('export'))}</a><a class="btn btn-secondary" href="/api/orders/${encodeURIComponent(order.id)}/evidence.zip" download>${icon('file')}${state.lang === 'zh' ? '证据包 ZIP' : '증거 ZIP'}</a></div></div>`; }
function regionMarkup(check, photo) {
  if (!check?.valid || check.photo_id !== photo?.id || check.revision !== state.order.revision || !Array.isArray(check.action?.region) || check.action.region.length !== 4) return '';
  const [x1, y1, x2, y2] = check.action.region.map(n => Math.min(1, Math.max(0, Number(n))));
  if ([x1, y1, x2, y2].some(n => !Number.isFinite(n)) || x2 <= x1 || y2 <= y1) return '';
  return `<div class="photo-region" style="left:${x1 * 100}%;top:${y1 * 100}%;width:${(x2 - x1) * 100}%;height:${(y2 - y1) * 100}%"><span>${esc(check.observation_verification?.mode === 'spatial_consensus' ? at('spatialRegion') : t('focusRegion'))}</span></div>`;
}
function renderEvidence(order) {
  const photo = selectedPhoto(); const allPhotos = photos(); const newest = latestPhoto(); const isCurrent = photo && photo.revision === order.revision && photo.id === newest?.id;
  const modelAvailable = !!state.health?.model?.available && !state.health?.inference?.busy; const locked = finalizedOrder(order); const checking = state.busy === 'inspect';
  const spatialCheck = spatialPhotoCheck(order, photo);
  const region = regionMarkup(order.latest_check, photo);
  const regionCaption = region ? `<p class="photo-region-caption">${icon('scan')}<span>${esc(order.latest_check.observation_verification?.mode === 'spatial_consensus' ? at('spatialRegion') : t('focusRegion'))}</span></p>` : '';
  const photoControls = order.demo_source ? '' : `<button class="btn btn-quiet btn-sm" data-action="camera" ${state.busy || locked ? 'disabled' : ''}>${icon('camera')}<span class="camera-label">${esc(t('camera'))}</span></button><button class="btn btn-secondary btn-sm" data-action="upload-photo" ${state.busy || locked ? 'disabled' : ''}>${icon('upload')}${esc(t(photo ? 'replacePhoto' : 'upload'))}</button>`;
  const publicGuidance = order.demo_source ? `<div class="quality-note">${esc(prText('fixedSource'))}</div>` : '';
  let hint = !photo ? 'inspectMissingPhoto' : !isCurrent ? 'inspectOldPhoto' : 'inspectSupport';
  return `<section class="panel evidence-panel" data-spatial-scope="workspace" aria-labelledby="evidence-heading"><div class="panel-header"><div class="panel-title">${icon('image')}<h2 id="evidence-heading">${esc(t('evidence'))}</h2></div><div class="evidence-tools">${photo ? `<button class="btn btn-secondary btn-sm" data-action="inspection-region" ${state.busy || locked || !isCurrent || order.status === 'completed' ? 'disabled' : ''}>${esc(KitGuardRegion.text(state.lang, 'title'))}</button>` : ''}${photoControls}</div></div>${publicGuidance}<div class="evidence-stage ${photo ? 'has-image' : ''}" id="evidence-dropzone" aria-label="${esc(order.demo_source ? prText('original') : t('dropPhoto'))}"><div class="canvas-topline"><span class="canvas-label">${icon('scan')} ${esc(photo ? (KitGuardRegion.isRegion(photo) ? KitGuardRegion.text(state.lang, 'preview') : t('original')) : 'KITGUARD / CAPTURE')}</span><span class="canvas-label">${photo ? `${esc(photo.width)} × ${esc(photo.height)}` : '12 SLOTS'}</span></div>${photo ? `<div class="photo-frame"><img src="${esc(imageUrl(photo))}" alt="${esc(`${order.title} · ${t('photoVersion', { revision: photo.revision })}`)}">${region}${spatialOverlayMarkup(spatialCheck, photo, 'workspace')}</div>` : `<div class="empty-evidence">${trayIllustration()}<h3>${esc(t('emptyPhotoTitle'))}</h3><p>${esc(t('emptyPhotoBody'))}</p><div class="capture-empty-actions">${photoControls}</div></div>`}</div>${photo ? KitGuardRegion.summary(photo, state.lang) : ''}${regionCaption}${spatialControlsMarkup(spatialCheck, photo, 'workspace')}${photo?.quality?.warning ? `<div class="quality-note">${esc(photo.quality.warning)}</div>` : ''}<div class="evidence-footer"><span>${icon(photo ? 'clock' : 'file')}${esc(photo ? formatDate(photo.created_at) : t('emptyPhotoFormats'))}</span><span>${photo ? `<span class="badge ${isCurrent ? 'revision' : 'invalid'}">${esc(t('photoVersion', { revision: photo.revision }))} · ${esc(t(isCurrent ? 'currentPhoto' : 'historicalPhoto'))}</span>` : esc(t('localNote'))}</span></div>${checking ? `<div class="loading-strip" role="status" aria-live="polite"><span class="spinner"></span><div>${esc(t('inspecting'))}<small>${esc(t('inspectingNote'))}</small></div><span id="elapsed" class="elapsed">${esc(t('elapsed', { seconds: Math.floor((Date.now() - state.startedAt) / 1000) }))}</span></div>` : `<div class="inspect-bar"><div class="inspect-meta"><strong>${esc(t('inspectPrompt'))}</strong>${esc(t(hint))}</div><button class="btn btn-primary" data-action="inspect" ${state.busy || !isCurrent || !modelAvailable || locked ? 'disabled' : ''}>${icon('scan')}${esc(t('inspect'))}</button></div>`}${allPhotos.length > 1 ? `<div class="photo-thumbnails" aria-label="${esc(t('photoHistory'))}">${[...allPhotos].reverse().map((p, index) => `<button class="thumbnail ${p.id === photo?.id ? 'active' : ''}" data-action="select-photo" data-id="${esc(p.id)}" aria-label="${esc(`${t('photoVersion', { revision: p.revision })} ${formatDate(p.created_at)}`)}" aria-pressed="${p.id === photo?.id}"><img src="${esc(imageUrl(p))}" alt="" loading="lazy"><span>R${esc(p.revision)} · ${esc(formatDate(p.created_at, 'time'))}</span></button>`).join('')}</div>` : ''}</section><div class="capture-hint">${icon('info')}<p>${esc(t('captureHint'))}</p></div>`;
}
function renderBOM(order) {
  const check = currentCheck(); const refsCount = PARTS.filter(p => !!order.references?.[p]).length;
  return `<section class="panel"><div class="check-heading"><h2>${esc(t('checkTitle'))}</h2><span class="badge revision">R${esc(order.revision)}</span></div><table class="bom-table"><thead><tr><th scope="col">${esc(t('part'))}</th><th scope="col">${esc(t('required'))}</th><th scope="col">${esc(t('observed'))}</th><th scope="col">${esc(t('result'))}</th></tr></thead><tbody>${PARTS.map(part => { const observed = check?.observed?.[part]; const known = Number.isInteger(observed); const delta = known ? observed - order.requirements[part] : null; return `<tr><td><span class="part-name"><span class="part-icon">${icon(part)}</span>${esc(partLabel(part))}</span></td><td>${order.requirements[part]}</td><td><span class="${known ? 'observed-value' : 'unknown-value'}" aria-label="${esc(known ? observed : t('unavailable'))}">${known ? observed : '—'}</span></td><td>${known ? delta === 0 ? `<span class="match-mark" aria-label="${esc(t('match'))}">${icon('check')}</span>` : `<span class="delta">${delta > 0 ? '+' : ''}${delta}</span>` : '<span class="unknown-value">—</span>'}</td></tr>`; }).join('')}</tbody></table><div class="bom-summary"><span>${esc(t('totalRequired'))}</span><strong>${esc(t('totalCount', { count: total(order.requirements) }))}</strong></div><button class="reference-link" data-action="references" ${state.busy || finalizedOrder() ? 'disabled' : ''}><span>${icon('grid')}${esc(t('manageReferences'))}</span><small>${esc(t('referencesCount', { count: refsCount }))}</small>${icon('chevron')}</button></section>`;
}
function renderAction(order) {
  const check = currentCheck(); const historical = selectedPhoto() && selectedPhoto().id !== latestPhoto()?.id; const completed = order.status === 'completed' && !historical; const stale = order.latest_check && !check;
  let title = latestPhoto() ? 'needsInspectTitle' : 'waitingTitle', message = latestPhoto() ? t('needsInspectMessage') : t('waitingMessage'), card = '', symbol = 'scan', button = '';
  if (stale) { title = 'staleTitle'; message = t('staleMessage'); symbol = 'branch'; }
  if (check) {
    if (check.decision === 'ready') { title = 'readyTitle'; message = KitGuardRegion.isRegion(selectedPhoto()) ? KitGuardRegion.text(state.lang, 'ready') : t('readyMessage'); card = 'action-ready'; symbol = 'check'; if (check.backend !== 'test' && !order.demo_source) button = `<button class="btn btn-primary btn-full" data-action="complete" ${state.busy ? 'disabled' : ''}>${icon('shield')}${esc(t('complete'))}</button>`; }
    else { title = check.decision === 'correct' ? 'correctTitle' : check.decision === 'manual' ? 'manualTitle' : 'recaptureTitle'; message = check.action?.message || (check.decision === 'manual' ? t('manualMessage') : ''); card = 'action-warning'; symbol = check.decision === 'manual' ? 'hand' : check.decision === 'correct' ? 'grid' : 'camera'; button = `<button class="btn btn-secondary btn-full" data-action="camera" ${state.busy || finalizedOrder() ? 'disabled' : ''}>${icon('camera')}${esc(t('followup'))}</button>`; }
  }
  if (historical) { title = 'historicalTitle'; message = t('historicalMessage'); symbol = 'clock'; button = `<button class="btn btn-secondary btn-full" data-action="show-latest">${icon('arrow')}${esc(t('showLatest'))}</button>`; }
  if (order.status === 'manual_reviewed' && !historical) { title = 'manual_reviewed'; message = t('manualRecordNote'); card = 'action-completed'; symbol = 'hand'; button = ''; }
  if (order.demo_source && check?.decision === 'ready') { title = 'match'; message = state.lang === 'zh' ? '公开照片中的观察数量与工单一致。此演示不能记录实物完工。' : '공개 사진의 관찰 수량이 일치합니다. 이 데모는 실물 완료를 기록할 수 없습니다.'; }
  if (order.demo_source && check && !historical) { button = ''; message = check.decision === 'ready' ? `${message} ${prText('nextPublic')}` : prText('nextPublic'); }
  if (completed) { title = 'completedTitle'; message = t('completedMessage'); card = 'action-completed'; symbol = 'shield'; button = ''; }
  if (state.busy === 'inspect') { title = 'inspecting'; message = t('inspectingNote'); card = ''; symbol = 'chip'; button = ''; }
  return `<section class="panel action-panel ${card}" aria-live="polite"><p class="action-label">${icon('branch')}${esc(t('nextAction'))}</p><div class="action-state-icon">${icon(symbol)}</div><h3>${esc(t(title))}</h3><p class="action-message">${esc(message)}</p>${check?.issues?.length ? `<ul class="issue-list">${check.issues.map(issue => `<li>${esc(issue)}</li>`).join('')}</ul>` : ''}${button}${order.status === 'manual_reviewed' && !historical ? manualReviewCard(order) : ''}${!historical && !completed && order.status !== 'manual_reviewed' ? manualReviewButton(order, check) : ''}${!historical ? reopenButton(order) : ''}${check?.backend === 'test' ? `<p class="model-error">${esc(t('testWarning'))}</p>` : ''}${check || completed ? `<p class="status-footnote">${esc(t('completionFootnote'))}</p>` : ''}${check ? `<div class="check-provenance"><span>${esc(check.model_label || t('model'))}</span><span>${esc(t('latency', { seconds: ((check.latency_ms || 0) / 1000).toFixed(1) }))}</span></div>` : ''}</section>`;
}
function renderHistory(order) { return auditRenderHistory(order); }
function renderProtocol() { return `<div class="protocol-card"><h3>${icon('shield')}${esc(t('protocolTitle'))}</h3><p>${esc(t('protocolText'))}</p><div class="protocol-tags"><span>${esc(t('protocol1'))}</span><span>${esc(t('protocol2'))}</span><span>${esc(t('protocol3'))}</span></div></div>`; }
function renderFooter() { return `<footer class="workspace-footer"><span>${icon('lock')}${esc(t('footerLocal'))} · KITGUARD${state.health?.version ? ` ${esc(state.health.version)}` : ''}</span><span>${esc(t('footerNote'))}</span></footer>`; }
function render() {
  document.documentElement.lang = state.lang === 'zh' ? 'zh-CN' : 'ko';
  document.title = `${state.order ? `${state.order.title} · ` : ''}KitGuard`;
  const content = !state.initialized ? `<div class="initial-loading"><span class="spinner"></span>${esc(t('loading'))}</div>` : state.order ? `${renderHeader(state.order)}${state.order.demo_source ? `<div class="notice-banner">${icon('info')}<span>${state.lang === 'zh' ? '公开照片演示：核验调用真实本地模型，但不能记录实物完工。' : '공개 사진 데모: 실제 로컬 모델로 검사하지만 실물 완료는 기록할 수 없습니다.'} <a href="${esc(state.order.demo_source.source_url)}" target="_blank" rel="noopener noreferrer">${esc(state.order.demo_source.license)}</a></span></div>` : ''}${state.health && !state.health.model?.available ? `<div class="notice-banner">${icon('chip')}<span>${esc(t('modelNotReady'))}</span><button class="btn btn-quiet btn-sm" data-action="model">${esc(t('modelTitle'))}${icon('chevron')}</button></div>` : ''}<div class="work-grid"><div class="evidence-column"><div>${renderEvidence(state.order)}</div>${renderHistory(state.order)}</div><aside class="check-column">${renderBOM(state.order)}${renderAction(state.order)}${renderPublicReview(state.order)}${renderProtocol()}</aside></div>${renderFooter()}` : renderWelcome();
  document.getElementById('app').innerHTML = `<div class="app-shell">${renderSidebar()}<div class="main-shell">${renderTopbar()}<main class="workspace" id="workspace" tabindex="-1">${state.error ? `<div class="error-banner" role="alert">${icon('alert')}<p>${esc(state.error).replaceAll('\n', '<br>')}</p><button class="icon-btn" data-action="dismiss-error" aria-label="${esc(t('close'))}">${icon('close')}</button></div>` : ''}${state.busy && state.busy !== 'inspect' ? `<div class="notice-banner" role="status"><span class="spinner"></span>${esc(t(state.busy === 'upload' || state.busy === 'reference' ? 'uploading' : 'working'))}</div>` : ''}${workflowRuntimeNotice()}${content}</main></div></div>`;
  renderOrderList();
}

function modalHeader(title, description) { return `<div class="modal-header"><div><h2>${esc(t(title))}</h2>${description ? `<p>${esc(t(description))}</p>` : ''}</div><button class="icon-btn" type="button" data-action="close-modal" aria-label="${esc(t('close'))}">${icon('close')}</button></div>`; }
function openModal(id, content) { const modal = document.getElementById(id); modal.innerHTML = content; if (!modal.open) modal.showModal(); return modal; }
function modalError(id, text) { const error = document.querySelector(`#${id} .modal-error`); if (error) { error.textContent = text; error.classList.add('visible'); } }
function quantitiesMarkup(requirements) { return `<div class="quantity-fields">${PARTS.map(part => `<label class="quantity-field"><span class="part-name"><span class="part-icon">${icon(part)}</span>${esc(partLabel(part))}</span><input name="${part}" type="number" min="0" max="3" step="1" inputmode="numeric" required value="${esc(requirements[part])}" aria-label="${esc(`${partLabel(part)} ${t('required')}`)}"></label>`).join('')}</div><div class="form-total">${esc(t('quantityLimit'))}</div>`; }
function getRequirements(form) { const counts = Object.fromEntries(PARTS.map(part => [part, Number(form.elements.namedItem(part).value)])); if (PARTS.some(part => form.elements.namedItem(part).value.trim() === '' || !Number.isInteger(counts[part]) || counts[part] < 0 || counts[part] > 3) || total(counts) < 1 || total(counts) > 12) throw new Error(t('invalidCounts')); return counts; }
function openNewOrder() { if (state.busy) return; openModal('order-dialog', `${modalHeader('createTitle', 'createDescription')}<form id="create-form"><div class="modal-content"><label class="field"><span>${esc(t('orderTitle'))}</span><input name="title" maxlength="100" required placeholder="${esc(t('orderPlaceholder'))}" value="${esc(`${t('defaultOrderTitle')} ${String(state.orders.length + 1).padStart(2, '0')}`)}"></label><p class="field-label">${esc(t('quantityLabel'))}</p>${quantitiesMarkup(DEFAULT_REQUIREMENTS)}<p class="form-note">${icon('info')}${esc(t('defaultNote'))}</p><div class="modal-error" role="alert"></div></div><div class="modal-footer"><button type="button" class="btn btn-quiet" data-action="close-modal">${esc(t('cancel'))}</button><button class="btn btn-primary" type="submit" data-mutate>${icon('plus')}${esc(t('createAction'))}</button></div></form>`); }
async function submitNewOrder(form) {
  let requirements; try { requirements = getRequirements(form); } catch (error) { modalError('order-dialog', error.message); return; }
  const title = form.elements.namedItem('title').value.trim(); if (!title) { modalError('order-dialog', t('invalidTitle')); return; }
  const result = await mutate('create', () => post('/api/orders', { title, requirements }), 'orderCreated', 'order-dialog');
  if (result) { state.selectedPhoto = null; state.sidebarOpen = false; document.getElementById('order-dialog').close(); render(); }
}
function openRevision(mode = 'structured') {
  if (!state.order || state.busy) return;
  state.revisionMode = mode; state.proposal = null;
  const order = state.order;
  const content = mode === 'structured' ? `<p class="field-label">${esc(t('quantityLabel'))}</p>${quantitiesMarkup(order.requirements)}<label class="field" style="margin-top:20px"><span>${esc(t('revisionReason'))}</span><textarea name="instruction" maxlength="500" placeholder="${esc(t('revisionPlaceholder'))}"></textarea></label><p class="form-note">${icon('branch')}${esc(t('directRevisionNote'))}</p>` : `<label class="field"><span>${esc(t('naturalLabel'))}</span><textarea name="instruction" maxlength="500" required placeholder="${esc(t('naturalPlaceholder'))}"></textarea></label><button type="button" class="btn btn-secondary" data-action="propose" data-mutate>${icon('chip')}${esc(t('propose'))}</button><div id="proposal-result"></div>`;
  openModal('revision-dialog', `${modalHeader('reviseTitle', 'reviseDescription')}<form id="revision-form" data-revision="${order.revision}"><div class="modal-content"><div class="revision-tabs" role="group" aria-label="${esc(t('revise'))}"><button type="button" class="${mode === 'structured' ? 'active' : ''}" data-action="revision-mode" data-mode="structured" aria-pressed="${mode === 'structured'}">${esc(t('structuredTab'))}</button><button type="button" class="${mode === 'natural' ? 'active' : ''}" data-action="revision-mode" data-mode="natural" aria-pressed="${mode === 'natural'}">${esc(t('naturalTab'))}</button></div>${content}<div class="modal-error" role="alert"></div></div><div class="modal-footer"><button type="button" class="btn btn-quiet" data-action="close-modal">${esc(t('cancel'))}</button><button type="submit" class="btn btn-primary" id="revision-submit" data-mutate ${mode === 'natural' ? 'disabled' : ''}>${icon('check')}${esc(t('approveRevision', { revision: order.revision + 1 }))}</button></div></form>`);
}
async function proposeRevision() {
  const form = document.getElementById('revision-form'); const instruction = form.elements.namedItem('instruction').value.trim();
  if (!instruction) { modalError('revision-dialog', t('invalidInstruction')); return; }
  const order = state.order; const baseRevision = Number(form.dataset.revision);
  const button = document.querySelector('[data-action="propose"]'); button.innerHTML = `<span class="spinner"></span>${esc(t('proposing'))}`;
  const result = await mutate('propose', () => post(`/api/orders/${encodeURIComponent(order.id)}/propose-revision`, { instruction, expected_revision: baseRevision }), null, 'revision-dialog');
  button.innerHTML = `${icon('chip')}${esc(t('propose'))}`;
  if (!result) { document.getElementById('revision-submit').disabled = true; return; }
  state.proposal = { ...result.proposal, instruction };
  const diffs = PARTS.filter(p => order.requirements[p] !== state.proposal.requirements[p]);
  document.getElementById('proposal-result').innerHTML = `<div class="proposal-card"><h3>${esc(t('proposalTitle'))}</h3><p>${esc(t('proposalReview'))}</p><div class="proposal-diffs">${diffs.length ? diffs.map(p => `<span>${esc(partLabel(p))} ${order.requirements[p]} → ${state.proposal.requirements[p]}</span>`).join('') : esc(t('noChanges'))}</div><p>${esc(state.proposal.explanation)}</p></div>`;
  document.getElementById('revision-submit').disabled = !diffs.length || form.elements.namedItem('instruction').value.trim() !== instruction;
}
async function submitRevision(form) {
  let requirements; const expectedRevision = Number(form.dataset.revision); let instruction = form.elements.namedItem('instruction').value.trim();
  if (state.revisionMode === 'natural') {
    if (!state.proposal || state.proposal.base_revision !== expectedRevision || state.order.revision !== expectedRevision || instruction !== state.proposal.instruction) { modalError('revision-dialog', t('proposalStale')); return; }
    requirements = state.proposal.requirements;
  } else { try { requirements = getRequirements(form); } catch (error) { modalError('revision-dialog', error.message); return; } }
  if (PARTS.every(p => requirements[p] === state.order.requirements[p])) { modalError('revision-dialog', t('noChanges')); return; }
  const result = await mutate('revise', () => post(`/api/orders/${encodeURIComponent(state.order.id)}/revise`, { requirements, instruction, expected_revision: expectedRevision }), 'revisionSaved', 'revision-dialog');
  if (result) { state.proposal = null; document.getElementById('revision-dialog').close(); }
}
function validateFile(file) { if (!file || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 12 * 1024 * 1024) throw new Error(t('invalidPhoto')); }
function pickPhoto() { if (!state.order || state.busy || state.order.demo_source) return; if (finalizedOrder()) return; const input = document.getElementById('photo-file'); input.value = ''; input.click(); }
async function uploadPhoto(file) {
  if (!state.order) { toast(t('noOrder')); return; }
  if (state.order.demo_source) { toast(prText('fixedSource')); return; }
  if (finalizedOrder()) return;
  try { validateFile(file); } catch (error) { showError(error); return; }
  const order = state.order; const form = new FormData(); form.append('photo', file); form.append('expected_revision', order.revision);
  await mutate('upload', () => post(`/api/orders/${encodeURIComponent(order.id)}/photos`, form), 'photoUploaded');
}
function openReferences() {
  if (!state.order || state.busy) return;
  openModal('references-dialog', `${modalHeader('referenceTitle', 'referenceDescription')}<div class="modal-content"><div class="reference-grid">${PARTS.map(part => { const ref = state.order.references?.[part]; const url = imageUrl(ref); return `<div class="reference-card"><div class="reference-image">${url ? `<img src="${esc(url)}" alt="${esc(partLabel(part))}">` : icon(part)}</div><div class="reference-card-bottom"><strong>${esc(partLabel(part))}</strong><button class="btn btn-quiet btn-sm" type="button" data-action="camera" data-part="${part}" aria-label="${esc(`${partLabel(part)} · ${t('camera')}`)}" data-mutate>${icon('camera')}</button><button class="btn btn-secondary" type="button" data-action="upload-reference" data-part="${part}" data-mutate>${icon('upload')}${esc(t(ref ? 'change' : 'register'))}</button></div></div>`; }).join('')}</div><p class="form-note">${icon('branch')}${esc(t('referenceNote'))}</p><div class="modal-error" role="alert"></div></div><div class="modal-footer"><button class="btn btn-primary" type="button" data-action="close-modal">${esc(t('close'))}</button></div>`);
}
function pickReference(part) { if (!PARTS.includes(part) || state.busy || finalizedOrder()) return; state.referencePart = part; const input = document.getElementById('reference-file'); input.value = ''; input.click(); }
async function uploadReference(file) {
  const part = state.referencePart; if (!part || !state.order) return;
  try { validateFile(file); } catch (error) { modalError('references-dialog', error.message); return; }
  const form = new FormData(); form.append('photo', file); form.append('expected_revision', state.order.revision);
  const result = await mutate('reference', () => post(`/api/orders/${encodeURIComponent(state.order.id)}/references/${part}`, form), 'referenceUploaded', 'references-dialog');
  if (result && document.getElementById('references-dialog').open) openReferences();
}
async function inspect() {
  const photo = selectedPhoto(); const order = state.order;
  if (!order || !photo || state.busy) return;
  await startInspectionJob();
}
function openComplete() {
  const check = currentCheck(); if (!check || check.decision !== 'ready' || check.backend === 'test' || state.order?.demo_source) { toast(t('noCurrentCheck')); return; }
  openModal('complete-dialog', `${modalHeader('completeTitle', 'completeDescription')}<form id="complete-form" data-check="${esc(check.id)}" data-revision="${state.order.revision}"><div class="modal-content"><span class="badge revision">${esc(t('confirmVersion', { revision: state.order.revision }))}</span><label class="confirm-box"><input type="checkbox" name="confirmed" required><span>${esc(t('confirmLabel'))}</span></label><p class="form-note">${icon('info')}${esc(t('completionFootnote'))}</p><div class="modal-error" role="alert"></div></div><div class="modal-footer"><button class="btn btn-quiet" type="button" data-action="close-modal">${esc(t('cancel'))}</button><button class="btn btn-primary" type="submit" data-mutate>${icon('shield')}${esc(t('confirmSubmit'))}</button></div></form>`);
}
async function submitComplete(form) {
  if (!form.elements.namedItem('confirmed').checked) { modalError('complete-dialog', t('confirmationRequired')); return; }
  const orderId = state.order.id; const checkId = form.dataset.check; const revision = Number(form.dataset.revision); const keyId = `${orderId}:${checkId}:${revision}`;
  if (!state.completionKeys.has(keyId)) state.completionKeys.set(keyId, crypto.randomUUID());
  const result = await mutate('complete', () => post(`/api/orders/${encodeURIComponent(orderId)}/complete`, { check_id: checkId, expected_revision: revision, confirmed: true, idempotency_key: state.completionKeys.get(keyId) }), 'completedSaved', 'complete-dialog');
  if (result) document.getElementById('complete-dialog').close();
}
function openModel() {
  const model = state.health?.model || {};
  openModal('model-dialog', `${modalHeader('modelTitle', 'modelDescription')}<div class="modal-content"><dl class="model-details"><dt>${esc(t('modelName'))}</dt><dd>${esc(model.label || t('modelUnknown'))}</dd><dt>${esc(t('modelAvailable'))}</dt><dd>${esc(t(model.available ? 'yes' : 'no'))}</dd><dt>${esc(t('modelLoaded'))}</dt><dd>${esc(t(model.loaded ? 'yes' : 'no'))}</dd><dt>${esc(t('modelPath'))}</dt><dd>${esc(model.path || '—')}</dd></dl>${model.error ? `<p class="model-error">${esc(model.error)}</p>` : ''}<p class="form-note">${icon('info')}${esc(t('modelNotReady'))}</p></div><div class="modal-footer"><button class="btn btn-quiet" type="button" data-action="close-modal">${esc(t('close'))}</button><button class="btn btn-primary" type="button" data-action="refresh-model">${icon('refresh')}${esc(t('refresh'))}</button></div>`);
}

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-action]'); if (!button || button.disabled) return;
  const action = button.dataset.action;
  if (action === 'language') {
    state.lang = button.dataset.lang === 'zh' ? 'zh' : 'ko'; try { localStorage.setItem('kitguard-language', state.lang); } catch { /* Private storage may be unavailable. */ }
    document.querySelectorAll('dialog[open]').forEach(d => d.close()); stopCamera(); render();
  } else if (action === 'spatial-toggle') spatialToggle(button);
  else if (action === 'new-order') openNewOrder();
  else if (action === 'audit-tab') { state.historyView = button.dataset.view === 'checks' ? 'checks' : 'events'; const panel = document.getElementById('audit-history-panel'); if (panel && state.order) panel.outerHTML = auditRenderHistory(state.order); }
  else if (action === 'audit-check' || action === 'audit-refresh') await auditOpenCheck(button.dataset.check, button.dataset.order || state.order?.id);
  else if (action === 'select-order') { if (!state.busy) await loadOrder(button.dataset.id); }
  else if (action === 'toggle-sidebar') { state.sidebarOpen = !state.sidebarOpen; render(); }
  else if (action === 'close-sidebar') { state.sidebarOpen = false; render(); if (typeof recoverInspectionState === 'function') await recoverInspectionState(); }
  else if (action === 'dismiss-error') { state.error = null; render(); }
  else if (action === 'close-modal') { const dialog = button.closest('dialog'); if (dialog?.id === 'camera-dialog') stopCamera(); dialog?.close(); }
  else if (action === 'revise') openRevision();
  else if (action === 'revision-mode') { if (!state.busy) openRevision(button.dataset.mode); }
  else if (action === 'propose') await proposeRevision();
  else if (action === 'upload-photo') pickPhoto();
  else if (action === 'inspection-region') { if (!state.busy && state.order && selectedPhoto()) { try { KitGuardRegion.open({order:state.order, photo:selectedPhoto(), lang:state.lang, save:async payload => { const result = await mutate('region', () => post(`/api/orders/${encodeURIComponent(state.order.id)}/inspection-region`, payload), null, 'region-dialog'); if (result) toast(KitGuardRegion.text(state.lang, 'saved')); return result; }}); } catch (error) { showError(error); } } }
  else if (action === 'references') openReferences();
  else if (action === 'upload-reference') pickReference(button.dataset.part);
  else if (action === 'select-photo') { state.selectedPhoto = button.dataset.id; render(); }
  else if (action === 'show-latest') { state.selectedPhoto = latestPhoto()?.id || null; render(); }
  else if (action === 'inspect') await inspect();
  else if (action === 'complete') openComplete();
  else if (action === 'camera') { if (!state.order?.demo_source || button.dataset.part) await openCamera(button.dataset.part || null); }
  else if (action === 'capture') await capturePhoto();
  else if (action === 'model') openModel();
  else if (action === 'refresh-model') { await refreshHealth(); render(); openModel(); }
  else if (action === 'refresh-workspace') { if (state.busy) return; try { await Promise.all([refreshHealth(), refreshOrders()]); if (state.order) await refreshCurrent(); else if (state.orders.length) await loadOrder(state.orders[0].id); state.error = null; render(); } catch (error) { showError(error); } }
});
document.addEventListener('submit', async event => {
  const form = event.target; if (!['create-form', 'revision-form', 'complete-form'].includes(form.id)) return;
  event.preventDefault(); if (state.busy) return;
  if (form.id === 'create-form') await submitNewOrder(form);
  if (form.id === 'revision-form') await submitRevision(form);
  if (form.id === 'complete-form') await submitComplete(form);
});
document.addEventListener('input', event => {
  if (event.target.id === 'order-search') { state.search = event.target.value; renderOrderList(); }
  if (event.target.closest('#revision-form') && event.target.name === 'instruction' && state.revisionMode === 'natural') { state.proposal = null; const submit = document.getElementById('revision-submit'); if (submit) submit.disabled = true; const proposal = document.getElementById('proposal-result'); if (proposal) proposal.replaceChildren(); }
});
document.getElementById('photo-file').addEventListener('change', event => { const file = event.target.files?.[0]; if (file) uploadPhoto(file); });
document.getElementById('reference-file').addEventListener('change', event => { const file = event.target.files?.[0]; if (file) uploadReference(file); });
document.getElementById('camera-dialog').addEventListener('close', event => { if (!event.target.open) stopCamera(); });
document.querySelectorAll('dialog').forEach(dialog => { dialog.addEventListener('click', event => { if (event.target === dialog) { if (dialog.id === 'camera-dialog' && !captureCanClose()) return; if (dialog.id === 'region-dialog' && !KitGuardRegion.canClose()) return; const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) { if (dialog.id === 'camera-dialog') stopCamera(); dialog.close(); } } }); });
document.addEventListener('dragover', event => { const zone = event.target.closest('#evidence-dropzone'); if (zone) { event.preventDefault(); if (!state.busy && !state.order?.demo_source) zone.classList.add('dragover'); } });
document.addEventListener('dragleave', event => { const zone = event.target.closest('#evidence-dropzone'); if (zone && !zone.contains(event.relatedTarget)) zone.classList.remove('dragover'); });
document.addEventListener('drop', event => { const zone = event.target.closest('#evidence-dropzone'); if (!zone) return; event.preventDefault(); zone.classList.remove('dragover'); if (state.busy) return; const file = event.dataTransfer?.files?.[0]; if (file) uploadPhoto(file); });
window.addEventListener('beforeunload', event => { if (state.busy && state.busy !== 'inspect') { event.preventDefault(); event.returnValue = ''; } stopCamera(); });

async function initialize() {
  render();
  const results = await Promise.allSettled([refreshHealth(), refreshOrders()]);
  if (results[1].status === 'rejected') state.error = results[1].reason.message;
  state.initialized = true;
  if (state.orders.length) { const requested = new URLSearchParams(location.search).get('order'); await loadOrder(state.orders.find(o => o.id === requested)?.id || state.orders[0].id); } else render();
}
document.addEventListener('DOMContentLoaded', initialize, { once: true });
