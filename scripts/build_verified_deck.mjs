import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const ROOT = process.cwd();
const OUT = path.join(ROOT, "docs/presentations/AcneLLM_Project_E2E_20min_Scientific_Verified.pptx");
const RENDER = path.join(ROOT, ".codex_tmp/acnellm_scientific_verified/artifact_render");
const W = 1280, H = 720, M = 56;
const FONT = "Aptos", SERIF = "Cambria";
const C = {
  paper: "#F8F6F0", ink: "#20252B", muted: "#606972", rule: "#B8B4AA",
  navy: "#1F4E79", navy2: "#7791A8", navyP: "#E8EDF1",
  wine: "#7A263A", wineP: "#F2E8EA", green: "#356859", greenP: "#E8F0ED",
  ochre: "#9A6A1E", ochreP: "#F4EEE2", white: "#FFFFFF", grayP: "#EFEEE9",
};

function txt(s, value, x, y, w, h, o={}) {
  const e = s.shapes.add({ geometry:"textbox", position:{left:x,top:y,width:w,height:h}, fill:"none", line:{style:"solid",fill:"none",width:0}, name:o.name });
  e.text = value;
  e.text.style = { fontSize:o.size??20, typeface:o.face??FONT, color:o.color??C.ink, bold:o.bold??false, italic:o.italic??false, alignment:o.align??"left", verticalAlignment:o.valign??"top" };
  return e;
}
function rect(s,x,y,w,h,o={}) {
  const e=s.shapes.add({geometry:o.geometry??"rect",position:{left:x,top:y,width:w,height:h},fill:o.fill??C.grayP,line:{style:"solid",fill:o.line??C.rule,width:o.lw??1}});
  if(o.text){e.text=o.text;e.text.style={fontSize:o.size??18,typeface:o.face??FONT,color:o.color??C.ink,bold:o.bold??false,alignment:o.align??"center",verticalAlignment:o.valign??"middle"};}
  return e;
}
function rule(s,x,y,w,color=C.rule,lw=1){return s.shapes.add({geometry:"line",position:{left:x,top:y,width:w,height:0},fill:"none",line:{style:"solid",fill:color,width:lw}});}
function seg(s,x1,y1,x2,y2,color=C.navy,lw=2){
  const left=Math.min(x1,x2),top=Math.min(y1,y2),width=Math.abs(x2-x1),height=Math.abs(y2-y1);
  return s.shapes.add({geometry:"line",position:{left,top,width,height},fill:"none",line:{style:"solid",fill:color,width:lw}});
}
function arrow(s,x,y,w=42,h=26,color=C.navy2){return s.shapes.add({geometry:"rightArrow",position:{left:x,top:y,width:w,height:h},fill:color,line:{style:"solid",fill:color,width:0}});}
function downArrow(s,x,y,w=28,h=24,color=C.navy2){return s.shapes.add({geometry:"downArrow",position:{left:x,top:y,width:w,height:h},fill:color,line:{style:"solid",fill:color,width:0}});}
function dot(s,x,y,r=5,color=C.navy){return rect(s,x-r,y-r,r*2,r*2,{geometry:"ellipse",fill:color,line:color,lw:0});}
function header(s,kicker,title,n){
  s.background.fill=C.paper;
  txt(s,kicker.toUpperCase(),M,23,500,22,{size:12,bold:true,color:C.wine});
  txt(s,title,M,50,1168,56,{size:34,bold:true,face:SERIF});
  rule(s,M,123,1168,C.ink,1.1);
  txt(s,"AcneLLM · bằng chứng kiểm tra trực tiếp từ repository",M,682,520,16,{size:10,color:C.muted});
  txt(s,String(n).padStart(2,"0"),1180,680,44,18,{size:11,color:C.muted,align:"right"});
}
function notes(s,talk,sources){s.speakerNotes.textFrame.setText(`${talk}\n\n[Sources]\n${sources.map(v=>`- ${v}`).join("\n")}`);s.speakerNotes.setVisible(true);}
function metric(s,value,label,x,y,w,color=C.navy){rect(s,x,y,w,98,{fill:C.white,line:C.rule});rule(s,x,y,w,color,3);txt(s,value,x+12,y+14,w-24,34,{size:27,bold:true,color,align:"center"});txt(s,label,x+12,y+57,w-24,28,{size:14,color:C.muted,align:"center"});}
function bullets(s,items,x,y,w,o={}){const gap=o.gap??42;items.forEach((v,i)=>{dot(s,x+5,y+i*gap+11,4,o.color??C.navy);txt(s,v,x+20,y+i*gap,w-20,gap-3,{size:o.size??17,color:o.textColor??C.ink});});}
function node(s,x,y,w,h,title,body,o={}){rect(s,x,y,w,h,{fill:o.fill??C.grayP,line:o.line??C.rule,lw:o.lw??1});txt(s,title,x+12,y+18,w-24,26,{size:o.titleSize??15,bold:true,color:o.color??C.navy,align:"center"});txt(s,body,x+12,y+62,w-24,h-78,{size:o.bodySize??17,color:o.bodyColor??C.ink,bold:o.bodyBold??false,align:"center",valign:"middle"});}
function vbar(s,label,value,max,x,y,w,h,color=C.navy,fmt=null){txt(s,label,x,y,w,22,{size:14});rect(s,x,y+25,w,h,{fill:C.grayP,line:C.grayP,lw:0});rect(s,x,y+25,Math.max(3,w*value/max),h,{fill:color,line:color,lw:0});txt(s,fmt??String(value),x+w+8,y+21,85,22,{size:14,bold:true,color});}
function timeline(s,items,y){const x0=70,x1=1210;rule(s,x0,y,x1-x0,C.navy,2);items.forEach((it,i)=>{const x=x0+i*(x1-x0)/(items.length-1);const tx=Math.max(M,Math.min(W-M-150,x-75));const bx=Math.max(M,Math.min(W-M-160,x-80));dot(s,x,y,9,i===items.length-1?C.wine:C.navy);txt(s,it[0],tx,y+24,150,24,{size:15,bold:true,color:i===items.length-1?C.wine:C.navy,align:"center"});txt(s,it[1],bx,y+54,160,52,{size:14,color:C.muted,align:"center"});});}

const deck=Presentation.create({slideSize:{width:W,height:H}});

// 1. Cover
{
  const s=deck.slides.add();s.background.fill=C.paper;
  txt(s,"ACNELLM · TECHNICAL SEMINAR",M,38,480,22,{size:13,bold:true,color:C.wine});rule(s,M,76,1168,C.ink,1.1);
  txt(s,"AcneLLM",M,140,720,72,{size:58,bold:true,face:SERIF});
  txt(s,"Từ dữ liệu, tinh chỉnh mô hình đến vận hành và kiểm định",M,228,1080,54,{size:34,bold:true,color:C.navy,face:SERIF});
  txt(s,"Một hệ thống tư vấn mụn chạy cục bộ, có truy xuất nguồn và kiểm soát an toàn nhiều tầng",M,300,1060,46,{size:22,color:C.muted});
  timeline(s,[["DỮ LIỆU","KB + 2 tập SFT"],["MÔ HÌNH","Intaker 3B + Generator 7B"],["VẬN HÀNH","Intake → RAG → SSE"],["KIỂM ĐỊNH","v2_full, 3 tuyến"]],474);
  txt(s,"Bản 20 phút · số liệu xác minh trực tiếp ngày 23-08-2026",M,642,620,24,{size:16,bold:true});
  notes(s,"30 giây. Deck kể toàn bộ vòng đời và chỉ dùng số liệu đã đối chiếu với code, JSONL, checkpoint, GGUF, index và báo cáo máy đọc được. Mỗi slide có nguồn trong speaker notes.",["E:\\project\\AcneLLM\\.audit\\SLIDE_FACT_CHECK_2026-08-23.md","E:\\project\\AcneLLM\\docs\\ARCHITECTURE_TRUTH.md"]);
}

// 2. Problem and contribution
{
  const s=deck.slides.add();header(s,"Câu hỏi nghiên cứu","Làm sao trả lời có ích mà vẫn kiểm soát tri thức, hành vi và rủi ro?",2);
  const cols=[56,452,848];
  [["01 · TRI THỨC","Mô hình không nên tự nhớ mọi hướng dẫn y khoa.","Giải pháp: sinh tăng cường truy hồi (Retrieval-Augmented Generation, RAG).",C.greenP,C.green],
   ["02 · HIỂU YÊU CẦU","Một lượt chat có thể là tư vấn, kiến thức, làm rõ hoặc từ chối.","Giải pháp: Intaker riêng trả JSON cấu trúc trong một lần suy luận.",C.navyP,C.navy],
   ["03 · AN TOÀN","An toàn không thể giao hoàn toàn cho một mô hình sinh văn bản.","Giải pháp: guardrail đầu vào + policy + hậu kiểm đầu ra.",C.wineP,C.wine]].forEach((v,i)=>{rect(s,cols[i],172,340,394,{fill:v[3],line:v[4],lw:2});txt(s,v[0],cols[i]+24,198,292,28,{size:17,bold:true,color:v[4]});txt(s,v[1],cols[i]+28,260,284,90,{size:22,bold:true,face:SERIF,align:"center"});rule(s,cols[i]+26,382,288,v[4],1.5);txt(s,v[2],cols[i]+28,412,284,112,{size:18,align:"center"});});
  rect(s,94,602,1092,38,{fill:C.ink,line:C.ink});txt(s,"Đóng góp hệ thống: tách trách nhiệm, lưu provenance và đánh giá từng tầng thay vì chấm một điểm chung.",112,610,1056,22,{size:17,bold:true,color:C.white,align:"center"});
  notes(s,"40 giây. AcneLLM không được trình bày như một chatbot đơn lẻ. Nó là kiến trúc phân vai: tri thức nằm trong KB, hiểu yêu cầu nằm ở Intaker, diễn đạt nằm ở Generator, còn policy và hậu kiểm nằm trong code.",["E:\\project\\AcneLLM\\src\\acne_llm\\di.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\intake.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\runtime.py"]);
}

// 3. Architecture
{
  const s=deck.slides.add();header(s,"Kiến trúc tổng thể","Hai LLM cục bộ là hai nút trong một pipeline có trạng thái",3);
  const xs=[44,244,444,644,844,1044];for(let i=0;i<5;i++)arrow(s,xs[i]+154,292,38,24);
  const d=[
    ["GIAO DIỆN","Next.js\nSSE client",C.grayP,C.navy],
    ["UNIFIED INTAKER","Qwen2.5-3B\nintent + fields",C.navyP,C.navy],
    ["ĐIỀU PHỐI","policy · history\nroute · mode",C.grayP,C.navy],
    ["RAG","Chroma + BM25\nBGE reranker",C.greenP,C.green],
    ["GENERATOR","Qwen2.5-7B\nstream tokens",C.ochreP,C.ochre],
    ["HOÀN TẤT","safety suffix\nSQLite + audit",C.wineP,C.wine],
  ];d.forEach((v,i)=>node(s,xs[i],194,164,220,v[0],v[1],{fill:v[2],line:v[3],color:v[3],lw:1.5}));
  rect(s,90,466,1100,116,{fill:C.ink,line:C.ink});txt(s,"Quy tắc phân vai",112,490,214,28,{size:22,bold:true,color:C.white,face:SERIF});
  txt(s,"Intaker cấu trúc hóa",340,486,210,30,{size:18,bold:true,color:C.navy2,align:"center"});txt(s,"RAG đưa bằng chứng",556,486,210,30,{size:18,bold:true,color:C.navy2,align:"center"});txt(s,"Generator diễn đạt",772,486,210,30,{size:18,bold:true,color:C.navy2,align:"center"});txt(s,"Code chốt an toàn",988,486,178,30,{size:18,bold:true,color:C.navy2,align:"center"});
  txt(s,"Dự phòng semantic/rule không gọi thêm LLM; phiên hội thoại production lưu bằng SQLite.",150,610,980,30,{size:20,bold:true,color:C.navy,align:"center"});
  notes(s,"55 giây. Dependency injection dựng đúng một UnifiedIntake; hai interface router/extractor cùng trỏ vào instance đó. Semantic router và rule fallback chạy local không gọi LLM. Generator là LLM thứ hai và duy nhất viết câu trả lời.",["E:\\project\\AcneLLM\\src\\acne_llm\\di.py","E:\\project\\AcneLLM\\src\\acne_llm\\config.py","E:\\project\\AcneLLM\\docs\\ARCHITECTURE_TRUTH.md"]);
}

// 4. Offline asset factories
{
  const s=deck.slides.add();header(s,"Xây dựng ngoại tuyến","Ba dây chuyền độc lập tạo ba tài sản phục vụ runtime",4);
  const cols=[56,452,848];
  [["CƠ SỞ TRI THỨC","6.835 tài liệu → 24.393 đoạn","Chroma + BM25","Cập nhật tri thức mà không huấn luyện lại",C.greenP,C.green],
   ["SFT INTAKER","985 golden + dữ liệu tổng hợp → 4.000 cuối","Qwen2.5-3B QLoRA","Dạy hợp đồng JSON và định tuyến",C.navyP,C.navy],
   ["SFT GENERATOR","mục tiêu 3.500 → 3.077 đạt","Qwen2.5-7B QLoRA","Dạy bám chứng cứ (grounding), hành vi và diễn đạt",C.ochreP,C.ochre]].forEach((v,i)=>{rect(s,cols[i],164,340,424,{fill:v[4],line:v[5],lw:2});txt(s,v[0],cols[i]+24,190,292,28,{size:17,bold:true,color:v[5]});txt(s,v[1],cols[i]+24,246,292,62,{size:24,bold:true,face:SERIF,align:"center"});arrow(s,cols[i]+145,330,50,28,v[5]);txt(s,v[2],cols[i]+24,382,292,38,{size:22,bold:true,align:"center"});rule(s,cols[i]+26,448,288,v[5],1.5);txt(s,v[3],cols[i]+26,480,288,64,{size:17,align:"center"});});
  txt(s,"SFT = tinh chỉnh có giám sát (supervised fine-tuning). KB không được xem là dữ liệu huấn luyện model.",100,618,1080,30,{size:19,bold:true,align:"center"});
  notes(s,"35 giây. Ba dây chuyền có vòng đời riêng. KB mang tri thức; Intaker SFT dạy hợp đồng dữ liệu; Generator SFT dạy hành vi. Không có bước nào nhồi toàn bộ KB vào trọng số model.",["E:\\project\\AcneLLM\\scripts\\build_kb.py","E:\\project\\AcneLLM\\research\\datagen\\intakedata\\pipeline.py","E:\\project\\AcneLLM\\research\\datagen\\roledatav2\\pipeline.py"]);
}

// 5. KB evidence
{
  const s=deck.slides.add();header(s,"Cơ sở tri thức","Hai chỉ mục khớp chính xác cùng 24.393 đoạn",5);
  metric(s,"6.835","tài liệu thô",56,154,190,C.green);metric(s,"6.796","qua ngưỡng chất lượng 0,3",264,154,238,C.green);metric(s,"24.393","đoạn cuối",520,154,190,C.green);metric(s,"24.393","Chroma vectors",728,154,190,C.green);metric(s,"24.393","BM25 items",936,154,190,C.green);
  txt(s,"Phân bố nguồn của 24.393 đoạn",56,286,470,28,{size:23,bold:true,face:SERIF});
  const src=[["Trang y khoa Việt",12359],["PubMed review",5218],["Blog",3571],["Trang y khoa Anh",2258],["Guideline + textbook",973],["Khác",14]];src.forEach((v,i)=>vbar(s,v[0],v[1],12359,56,330+i*42,470,16,i<4?C.green:C.ochre,v[1].toLocaleString("vi-VN")));
  rect(s,700,300,524,284,{fill:C.white,line:C.rule});txt(s,"Pipeline build thực",726,326,472,28,{size:23,bold:true,face:SERIF});
  const steps=[["1","lọc chất lượng / phạm vi"],["2","làm sạch + phát hiện ngôn ngữ"],["3","dedupe exact / near-duplicate"],["4","chunk 200 · overlap 40 · min 50"],["5","rebuild prev/next + hai index"]];steps.forEach((v,i)=>{rect(s,730,374+i*38,28,28,{geometry:"ellipse",fill:i===4?C.green:C.navy,line:i===4?C.green:C.navy,lw:0,text:v[0],size:14,bold:true,color:C.white});txt(s,v[1],774,376+i*38,394,24,{size:17,bold:i===4});});
  txt(s,"Bất biến: Chroma và BM25 phải cùng snapshot chunk_id; kiểm tra live hiện đạt 24.393 = 24.393.",140,618,1000,30,{size:19,bold:true,color:C.green,align:"center"});
  notes(s,"50 giây. Số liệu được đếm trực tiếp từ JSONL, Chroma collection và BM25 pickle. Tỷ trọng nguồn chỉ mô tả độ phủ, không đại diện độ tin cậy. Guideline và textbook ít hơn nhưng runtime có lượt truy hồi ưu tiên riêng.",["E:\\project\\AcneLLM\\data\\raw\\documents.jsonl","E:\\project\\AcneLLM\\data\\raw\\chunks.jsonl","E:\\project\\AcneLLM\\data\\bm25_index.pkl","E:\\project\\AcneLLM\\data\\chroma_db","E:\\project\\AcneLLM\\scripts\\build_kb.py"]);
}

// 6. Intaker data funnel
{
  const s=deck.slides.add();header(s,"Dữ liệu Intaker","4.000 là corpus cuối — không phải tổng số ứng viên",6);
  const xs=[54,270,486,702,918];for(let i=0;i<4;i++)arrow(s,xs[i]+164,290,44,26);
  const stages=[
    ["GOLDEN THÔ","985 dòng","nhãn cũ để relabel",C.grayP,C.navy],
    ["SINH + RELABEL","GPT-4o-mini","tối đa 4 lần / slot",C.navyP,C.navy],
    ["AUDIT FULL-MODE","11.980 sự kiện","4.149 accept · 7.588 reject · 239 error",C.ochreP,C.ochre],
    ["PURGE","−149","trùng evaluation sau accept",C.wineP,C.wine],
    ["CORPUS CUỐI","4.000","836 golden · 3.164 synthetic",C.greenP,C.green],
  ];stages.forEach((v,i)=>{node(s,xs[i],194,176,220,v[0],`${v[1]}\n${v[2]}`,{fill:v[3],line:v[4],color:v[4],lw:1.5,bodyBold:true});});
  rect(s,54,470,1170,116,{fill:C.white,line:C.rule});txt(s,"Phân bố intent cuối",82,496,220,26,{size:20,bold:true,face:SERIF});
  [["advise",2000,C.navy],["knowledge",800,C.green],["clarify",700,C.ochre],["reject",500,C.wine]].forEach((v,i)=>{const x=320+i*218;txt(s,v[0],x,494,130,22,{size:15,bold:true,color:v[2],align:"center"});rect(s,x,528,150,24,{fill:C.grayP,line:C.grayP,lw:0});rect(s,x,528,150*v[1]/2000,24,{fill:v[2],line:v[2],lw:0});txt(s,v[1].toLocaleString("vi-VN"),x+154,528,64,22,{size:13,bold:true,color:v[2],align:"center"});});
  txt(s,"Split cuối: 3.600 train / 400 validation · duplicate ID = 0 · exact overlap với evaluation = 0",94,616,1092,30,{size:18,bold:true,color:C.green,align:"center"});
  notes(s,"50 giây. Audit full-mode có 11.980 sự kiện, không phải 11.980 mẫu duy nhất; toàn file còn có smoke/limit. 4.149 accept tích lũy qua nhiều lượt chạy; pipeline loại 149 dòng trùng evaluation sau accept, còn đúng 4.000 bản ghi cuối.",["E:\\project\\AcneLLM\\data\\golden_extraction_gen.jsonl","E:\\project\\AcneLLM\\research\\datagen\\intakedata\\output\\intake\\intake.records.jsonl","E:\\project\\AcneLLM\\research\\datagen\\intakedata\\output\\intake\\audit.jsonl","E:\\project\\AcneLLM\\research\\datagen\\intakedata\\output\\intake\\summary.json","E:\\project\\AcneLLM\\research\\datagen\\intakedata\\pipeline.py"]);
}

// 7. Intaker training
{
  const s=deck.slides.add();header(s,"Tinh chỉnh mô hình 1","Intaker 3B học hợp đồng JSON bằng QLoRA",7);
  rect(s,56,156,360,442,{fill:C.navyP,line:C.navy,lw:2});txt(s,"THIẾT LẬP HUẤN LUYỆN",82,184,308,24,{size:16,bold:true,color:C.navy});txt(s,"Qwen2.5-3B-Instruct",82,226,308,38,{size:27,bold:true,face:SERIF,align:"center"});
  bullets(s,["4-bit NF4 qua Unsloth","LoRA r=16 · α=32 · dropout 0,05","7 projection targets","max sequence 2.048","batch 8 × grad accumulation 2","3 epoch · learning rate 2e-4"],84,300,296,{size:17,gap:40,color:C.navy});
  rect(s,448,156,464,442,{fill:C.white,line:C.rule});txt(s,"ĐƯỜNG HỌC THẬT TỪ CHECKPOINT",474,184,412,24,{size:16,bold:true,color:C.navy});
  const px=486,py=506,pw=378,ph=230;
  const tr=[[10,.3952],[100,.11],[200,.075],[300,.058],[400,.050],[500,.046],[600,.044],[675,.0432]];
  const ev=[[500,.03152],[600,.03094],[675,.0313]];
  const mapX=v=>px+pw*v/675,mapY=v=>py-ph*v/.42;
  [0,.1,.2,.3,.4].forEach(v=>{const yy=mapY(v);seg(s,px,yy,px+pw,yy,v===0?C.rule:"#DEDCD5",v===0?1:0.7);txt(s,v.toFixed(2).replace(".",","),px-58,yy-7,50,14,{size:9,color:C.muted,align:"right"});});
  [0,100,200,300,400,500,600,675].forEach(v=>{const xx=mapX(v);seg(s,xx,py,xx,py+5,C.rule,0.8);txt(s,String(v),xx-18,py+7,36,14,{size:9,color:C.muted,align:"center"});});
  seg(s,px,py-ph,px,py,C.rule,1);txt(s,"loss",px-58,258,50,16,{size:10,color:C.muted,align:"right"});txt(s,"step",828,528,46,16,{size:10,color:C.muted,align:"right"});
  for(let i=0;i<tr.length-1;i++)seg(s,mapX(tr[i][0]),mapY(tr[i][1]),mapX(tr[i+1][0]),mapY(tr[i+1][1]),C.navy,3);
  tr.forEach(v=>dot(s,mapX(v[0]),mapY(v[1]),3,C.navy));
  for(let i=0;i<ev.length-1;i++)seg(s,mapX(ev[i][0]),mapY(ev[i][1]),mapX(ev[i+1][0]),mapY(ev[i+1][1]),C.wine,2);
  ev.forEach(v=>dot(s,mapX(v[0]),mapY(v[1]),4,C.wine));
  txt(s,"train",720,220,60,20,{size:13,bold:true,color:C.navy});txt(s,"validation",786,220,88,20,{size:13,bold:true,color:C.wine});
  rect(s,714,430,116,36,{fill:C.white,line:C.wine,lw:1});txt(s,"best val\n600 · 0,03094",720,435,104,26,{size:10,bold:true,color:C.wine,align:"center"});
  txt(s,"675 · 0,0432",780,470,82,16,{size:10,bold:true,color:C.navy,align:"right"});
  rect(s,944,156,280,442,{fill:C.greenP,line:C.green,lw:2});txt(s,"GÓI ĐÃ LƯU",968,184,232,24,{size:16,bold:true,color:C.green});metric(s,"600","best checkpoint",970,230,228,C.green);metric(s,"0,03094","best validation loss",970,346,228,C.green);txt(s,"GGUF Q4_K_M\n1.929.902.592 byte",968,470,232,58,{size:20,bold:true,align:"center"});txt(s,"Ollama: acne-intaker",968,548,232,24,{size:17,bold:true,color:C.green,align:"center"});
  txt(s,"Trạng thái đã lưu: 675 steps · train loss cuối 0,04316 · runtime 1.160,76 giây",120,624,1040,28,{size:18,bold:true,align:"center"});
  notes(s,"55 giây. LoRA là thích nghi hạng thấp, chỉ huấn luyện ma trận nhỏ trên model 4-bit. Đường loss lấy từ trainer state trong gói mô hình, không suy từ notebook. Best checkpoint là 600, validation loss 0,03094; GGUF cuối khoảng 1,93 GB.",["E:\\project\\AcneLLM\\research\\notebooks\\intaker\\finetune_intake_qwen25_3b_q4.ipynb","E:\\project\\AcneLLM\\model\\intaker\\qwen25_intake_lora.zip","E:\\project\\AcneLLM\\model\\intaker\\MANIFEST.json","E:\\project\\AcneLLM\\model\\intaker\\Qwen2.5-3B-Instruct.Q4_K_M.gguf"]);
}

// 8. Intaker role and contract
{
  const s=deck.slides.add();header(s,"Hợp đồng Intaker","Một lần suy luận dùng chung cho định tuyến và trích xuất",8);
  node(s,56,190,240,260,"ĐẦU VÀO","lượt hiện tại\n+ lịch sử user/assistant\nđã chọn và rút gọn",{fill:C.grayP,line:C.rule,color:C.navy});arrow(s,314,304,48,28);
  node(s,386,166,310,308,"UNIFIED INTAKER","intent\nconfidence\ndescription nguyên văn\ncontext\nclinical fields",{fill:C.navyP,line:C.navy,color:C.navy,lw:2,bodyBold:true,bodySize:19});arrow(s,714,304,48,28);
  node(s,786,190,214,260,"ROUTE","advise\nknowledge\nclarify\nreject",{fill:C.greenP,line:C.green,color:C.green,bodyBold:true});
  node(s,1024,190,200,260,"FACTS","age · sex\nlesion · area\nmedication…",{fill:C.ochreP,line:C.ochre,color:C.ochre,bodyBold:true});
  rect(s,118,506,1044,86,{fill:C.ink,line:C.ink});txt(s,"Không có hai LLM intake",140,528,260,28,{size:21,bold:true,color:C.white,face:SERIF});txt(s,"router và extractor cùng tham chiếu một UnifiedIntake; lỗi format/model → semantic → rule.",414,526,720,32,{size:19,bold:true,color:C.navy2,align:"center"});
  txt(s,"Lược đồ là hợp đồng dữ liệu cho route, safety, RAG và session — không phải chẩn đoán lâm sàng.",120,618,1040,34,{size:19,bold:true,color:C.navy,align:"center"});
  notes(s,"40 giây. Unified Intaker nhận lượt hiện tại cùng lịch sử user/assistant đã chọn và rút gọn; không có một history schema đã chuẩn hóa riêng. Trường description giữ nguyên lượt hiện tại. JSON là hợp đồng dữ liệu cho các consumer downstream, không phải nhãn chẩn đoán.",["E:\\project\\AcneLLM\\src\\acne_llm\\di.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\unified_intake.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\intake.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\intake_contract.py"]);
}

// 9. Generator data funnel
{
  const s=deck.slides.add();header(s,"Dữ liệu Generator-v2","Quy trình hai pha đạt 3.077 mẫu nhưng chưa hoàn thành mục tiêu",9);
  metric(s,"3.500","mục tiêu",56,152,180,C.ochre);metric(s,"3.335","skeleton pha 1",254,152,200,C.ochre);metric(s,"3.077","record đạt pha 2",472,152,200,C.green);metric(s,"1.460","rejected attempts của summary",690,152,246,C.wine);metric(s,"3","post-gate failures",954,152,270,C.wine);
  const xs=[56,272,488,704,920];for(let i=0;i<4;i++)arrow(s,xs[i]+164,370,44,26,C.ochre);
  const d=[
    ["ĐẦU VÀO","case type\nanchor context",C.grayP,C.navy],
    ["PHA 1","DeepSeek v4 Flash\nuser + required points",C.ochreP,C.ochre],
    ["ĐÓNG BĂNG","3.335 skeletons\nmax 4 attempts",C.grayP,C.navy],
    ["PHA 2","DeepSeek v4 Flash\ngrounded answer",C.ochreP,C.ochre],
    ["FINAL","3.077 accepted\nstatus: incomplete",C.wineP,C.wine],
  ];d.forEach((v,i)=>node(s,xs[i],300,176,210,v[0],v[1],{fill:v[2],line:v[3],color:v[3],lw:1.5,bodyBold:true}));
  rect(s,96,548,1088,56,{fill:C.white,line:C.rule});txt(s,"Chia theo group/source",122,565,210,24,{size:18,bold:true,face:SERIF});txt(s,"2.616 train",360,565,180,24,{size:18,bold:true,color:C.navy,align:"center"});txt(s,"246 validation",570,565,180,24,{size:18,bold:true,color:C.green,align:"center"});txt(s,"215 tập giữ lại",780,565,180,24,{size:18,bold:true,color:C.ochre,align:"center"});txt(s,"không rò group",990,565,160,24,{size:17,bold:true,color:C.wine,align:"center"});
  txt(s,"3.707 dòng audit reject là lịch sử tích lũy (1.431 ID), không phải số reject của lượt summary hiện tại.",116,624,1048,28,{size:17,bold:true,color:C.wine,align:"center"});
  notes(s,"50 giây. Dữ liệu Generator chưa hoàn thành mục tiêu. Pha một có 3.335 skeleton; pha hai còn 3.077 bản ghi đạt. Summary có 1.460 lần thử bị loại và ba lỗi anchor_pair_corpus, nên trạng thái vẫn incomplete. Audit 3.707 dòng là lịch sử tích lũy.",["E:\\project\\AcneLLM\\research\\datagen\\roledatav2\\config.py","E:\\project\\AcneLLM\\research\\datagen\\roledatav2\\pipeline.py","E:\\project\\AcneLLM\\research\\datagen\\roledatav2\\output\\skeletons.jsonl","E:\\project\\AcneLLM\\research\\datagen\\roledatav2\\output\\roledata.train.jsonl","E:\\project\\AcneLLM\\research\\datagen\\roledatav2\\output\\generation_summary.json","E:\\project\\AcneLLM\\research\\datagen\\roledatav2\\output\\rejected.audit.jsonl"]);
}

// 10. Generator training
{
  const s=deck.slides.add();header(s,"Tinh chỉnh mô hình 2","Generator-v2: trạng thái huấn luyện đã lưu khác notebook hiện tại",10);
  rect(s,56,156,342,444,{fill:C.ochreP,line:C.ochre,lw:2});txt(s,"NOTEBOOK HIỆN TẠI",80,184,294,24,{size:16,bold:true,color:C.ochre});txt(s,"Qwen2.5-7B-Instruct",80,226,294,36,{size:26,bold:true,face:SERIF,align:"center"});bullets(s,["4-bit NF4 · QLoRA","r=16 · α=32 · dropout 0,05","max sequence 3.072","batch 1 × grad accumulation 16","learning rate 2e-4","khai báo 2 epoch"],82,294,286,{size:17,gap:41,color:C.ochre});
  rect(s,426,156,486,444,{fill:C.white,line:C.rule});txt(s,"TRAINER STATE / ADAPTER",452,184,434,24,{size:16,bold:true,color:C.navy});
  const px=468,py=506,pw=390,ph=224;
  const tr=[[10,1.42],[50,.90],[100,.74],[150,.66],[200,.61],[250,.58],[300,.56],[350,.55],[400,.54],[450,.53]];
  const ev=[[50,.91],[100,.83],[150,.80],[200,.78],[250,.76],[300,.7477],[350,.76],[400,.75],[450,.75]];
  const mx=v=>px+pw*v/450,my=v=>py-ph*v/1.5;
  [0,.5,1,1.5].forEach(v=>{const yy=my(v);seg(s,px,yy,px+pw,yy,v===0?C.rule:"#DEDCD5",v===0?1:0.7);txt(s,v.toFixed(1).replace(".",","),px-58,yy-7,50,14,{size:9,color:C.muted,align:"right"});});
  [0,100,200,300,400,450].forEach(v=>{const xx=mx(v);seg(s,xx,py,xx,py+5,C.rule,0.8);txt(s,String(v),xx-18,py+7,36,14,{size:9,color:C.muted,align:"center"});});
  seg(s,px,py-ph,px,py,C.rule,1);txt(s,"loss",px-58,252,50,16,{size:10,color:C.muted,align:"right"});txt(s,"step",822,520,38,14,{size:10,color:C.muted,align:"right"});
  for(let i=0;i<tr.length-1;i++)seg(s,mx(tr[i][0]),my(tr[i][1]),mx(tr[i+1][0]),my(tr[i+1][1]),C.navy,3);
  for(let i=0;i<ev.length-1;i++)seg(s,mx(ev[i][0]),my(ev[i][1]),mx(ev[i+1][0]),my(ev[i+1][1]),C.wine,2);
  tr.forEach(v=>dot(s,mx(v[0]),my(v[1]),3,C.navy));ev.forEach(v=>dot(s,mx(v[0]),my(v[1]),3,C.wine));
  txt(s,"train",712,220,56,20,{size:13,bold:true,color:C.navy});txt(s,"validation",774,220,86,20,{size:13,bold:true,color:C.wine});
  rect(s,668,340,126,36,{fill:C.white,line:C.wine,lw:1});txt(s,"best val\n300 · 0,74770",674,345,114,26,{size:10,bold:true,color:C.wine,align:"center"});
  txt(s,"train cuối 0,53",766,430,90,16,{size:10,bold:true,color:C.navy,align:"right"});
  txt(s,"3-epoch / 492-step schedule",474,532,380,22,{size:15,bold:true});txt(s,"early stop: step 450 · epoch 2,746",474,558,380,22,{size:15,bold:true,color:C.wine});
  rect(s,940,156,284,444,{fill:C.wineP,line:C.wine,lw:2});txt(s,"TRẠNG THÁI ĐÃ LƯU",966,184,232,24,{size:16,bold:true,color:C.wine});metric(s,"300","best checkpoint",968,230,228,C.wine);metric(s,"0,74770","best validation loss",968,346,228,C.wine);txt(s,"root adapter hash\n= checkpoint 300",968,466,228,52,{size:18,bold:true,align:"center"});txt(s,"GGUF Q4_K_M\n4.683.073.568 byte",968,534,228,46,{size:17,bold:true,align:"center"});
  txt(s,"Kết luận tái lập: notebook mô tả ý định; trainer state + adapter hash là bằng chứng đã lưu.",118,624,1044,28,{size:18,bold:true,color:C.wine,align:"center"});
  notes(s,"55 giây. Notebook hiện ghi hai epoch, nhưng trainer state lưu lịch ba epoch và dừng ở step 450; checkpoint tốt nhất là 300, root adapter hash khớp checkpoint này. Đường loss và hash lấy từ thư mục adapter thật, không suy từ notebook.",["E:\\project\\AcneLLM\\research\\notebooks\\generatorv2\\finetune_role_v2_qwen25_T4.ipynb","E:\\project\\AcneLLM\\model\\generator\\qwen25_acne_role_v2_lora","E:\\project\\AcneLLM\\model\\generator\\acnellm-role-v2.Q4_K_M.gguf"]);
}

// 11. Version truth map
{
  const s=deck.slides.add();header(s,"Sự thật phiên bản","Gói đã kiểm định và model triển khai mặc định chưa đồng nhất",11);
  const rows=[
    ["GÓI V2","acnellm-role-v2.Q4_K_M.gguf","SHA-256 71731A…69E7","đầu ra QLoRA Generator-v2",C.greenP,C.green],
    ["PROTOCOL v2_full","acne-generator-v2","system prompt v4.a","đã dùng cho ablation 145 × 6",C.navyP,C.navy],
    ["RUNTIME MẶC ĐỊNH","acne-generator","Modelfile.full → GGUF round 1","config + Compose + ollama-init",C.wineP,C.wine],
  ];rows.forEach((v,i)=>{const y=166+i*132;rect(s,56,y,1168,104,{fill:v[4],line:v[5],lw:1.5});txt(s,v[0],80,y+18,210,24,{size:16,bold:true,color:v[5]});txt(s,v[1],300,y+14,330,32,{size:23,bold:true,face:SERIF});txt(s,v[2],300,y+54,330,24,{size:16,color:C.muted});txt(s,v[3],674,y+30,510,42,{size:19,bold:true,align:"center"});});
  txt(s,"ĐƯỢC DÙNG BỞI",548,274,184,20,{size:12,bold:true,color:C.navy,align:"center"});
  txt(s,"KHÔNG KHỚP",548,406,184,20,{size:12,bold:true,color:C.wine,align:"center"});
  rect(s,110,588,1060,54,{fill:C.ink,line:C.ink});txt(s,"Vì vậy: kết quả v2_full gắn với acne-generator-v2; không tự động đại diện Compose mặc định hiện tại.",132,603,1016,26,{size:18,bold:true,color:C.white,align:"center"});
  notes(s,"40 giây. v2_full đánh giá acne-generator-v2, nhưng config và Compose mặc định là acne-generator; ollama-init dựng model mặc định từ Modelfile.full dùng GGUF round một. Hai nhãn quan hệ thay mũi tên nhân quả: artifact v2 được protocol dùng, còn runtime mặc định không khớp protocol.",["E:\\project\\AcneLLM\\model\\generator\\Modelfile","E:\\project\\AcneLLM\\model\\generator\\Modelfile.full","E:\\project\\AcneLLM\\docker\\ollama-init.sh","E:\\project\\AcneLLM\\docker-compose.yml","E:\\project\\AcneLLM\\src\\acne_llm\\config.py","E:\\project\\AcneLLM\\research\\evaluation\\reports\\v2_full\\summary.json"]);
}

// 12. Runtime sequence
{
  const s=deck.slides.add();header(s,"Vận hành đầu-cuối (E2E)","Một yêu cầu đi qua bốn pha: hiểu, tìm bằng chứng, sinh, chốt",12);
  const stages=[
    ["1 · INTAKE","guardrail → UnifiedIntake → session fold","RouteDecision + facts",C.navyP,C.navy],
    ["2 · RETRIEVAL","Chroma + BM25 → RRF → BGE","tối đa 5 đoạn có provenance",C.greenP,C.green],
    ["3 · GENERATION","prompt + context → Ollama stream","token SSE + sources",C.ochreP,C.ochre],
    ["4 · FINALIZE","safety suffix → SQLite → audit","done event + trạng thái",C.wineP,C.wine],
  ];stages.forEach((v,i)=>{const x=56+i*296;if(i<3)arrow(s,x+244,324,42,26,v[5]);rect(s,x,174,252,328,{fill:v[3],line:v[4],lw:2});txt(s,v[0],x+22,202,208,26,{size:17,bold:true,color:v[4]});txt(s,v[1],x+24,270,204,82,{size:20,bold:true,face:SERIF,align:"center"});rule(s,x+24,378,204,v[4],1.5);txt(s,v[2],x+24,410,204,56,{size:17,align:"center"});});
  timeline(s,[["prepare","một lần"],["token","nhiều sự kiện"],["sources","sau generation"],["done","sau persist"]],572);
  notes(s,"45 giây. Runtime chuẩn bị route, retrieval và prompt một lần trước khi stream. Retrieval có thể trả ít hơn năm đoạn hoặc không có context sau các cổng lọc. Token phát nhiều lần; source event tới sau generation; safety suffix và persist chạy trước done.",["E:\\project\\AcneLLM\\src\\acne_llm\\chat\\orchestrator.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\runtime.py"]);
}

// 13. Intake order and safety
{
  const s=deck.slides.add();header(s,"Intake và an toàn","Chính sách thuốc được kiểm tại ba thời điểm có thêm thông tin",13);
  rule(s,190,292,900,C.wine,3);
  const checks=[
    ["01 · TRƯỚC INTAKER","Lượt hiện tại","thuật ngữ safety + tiền kiểm xác định",190],
    ["02 · SAU TRÍCH XUẤT","Structured facts","kiểm lại khi đã có medication / pregnancy / allergy",640],
    ["03 · SAU GỘP PHIÊN","Hồ sơ đã xác nhận","kiểm lại với lịch sử và profile đã fold",1090],
  ];
  checks.forEach((v,i)=>{dot(s,v[3],292,12,C.wine);txt(s,v[0],v[3]-150,176,300,26,{size:17,bold:true,color:C.wine,align:"center"});txt(s,v[1],v[3]-154,226,308,30,{size:24,bold:true,face:SERIF,align:"center"});txt(s,v[2],v[3]-160,330,320,82,{size:18,align:"center"});});
  rect(s,90,482,1100,104,{fill:C.navyP,line:C.navy,lw:1.3});txt(s,"Dự phòng tính sẵn sàng",116,504,264,28,{size:20,bold:true,color:C.navy,face:SERIF});txt(s,"UnifiedIntake → semantic → rule; semantic/rule không gọi LLM.",394,500,750,30,{size:19,bold:true,align:"center"});txt(s,"medication_safety_refusal là policy chuyên biệt, không phải một regex chung cho mọi safety.",394,538,750,30,{size:17,color:C.muted,align:"center"});
  notes(s,"45 giây. Chính sách thuốc được kiểm trên lượt hiện tại, sau extracted facts và sau session fold vì thông tin thuốc có thể xuất hiện ở cả ba lớp. Chuỗi UnifiedIntake → semantic → rule là fallback tính sẵn sàng; medication_safety_refusal là chính sách chuyên biệt.",["E:\\project\\AcneLLM\\src\\acne_llm\\chat\\intake.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\_safety.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\routing\\semantic_router.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\session\\fold.py"]);
}

// 14. Retrieval
{
  const s=deck.slides.add();header(s,"RAG khi vận hành","Truy hồi rộng trước, xếp hạng lại hẹp sau",14);
  const xs=[52,246,440,634,828,1022];for(let i=0;i<5;i++)arrow(s,xs[i]+144,302,42,26,C.green);
  const d=[["QUERY","current turn\n+ extracted entities"],["DENSE + BM25","semantic + keyword\n24.393 shared IDs"],["RRF","hợp nhất hạng\n25 candidates"],["EXTRA PASSES","guideline luôn chạy\nsafety khi có term"],["BGE RERANK","bge-reranker-v2-m3\nnoise + source + score"],["CONTEXT","≤ 5 đoạn\ntối đa 6.000 ký tự"]];d.forEach((v,i)=>node(s,xs[i],196,154,232,v[0],v[1],{fill:i===5?C.ochreP:C.greenP,line:i===5?C.ochre:C.green,color:i===5?C.ochre:C.green,lw:1.4}));
  rect(s,76,482,1128,116,{fill:C.white,line:C.rule});txt(s,"Hợp nhất hạng nghịch đảo (Reciprocal Rank Fusion, RRF)",104,508,480,26,{size:20,bold:true,face:SERIF});txt(s,"không cần chuẩn hóa trực tiếp điểm cosine và BM25",608,508,552,26,{size:18,bold:true,align:"center"});txt(s,"Guideline pass chạy cho mọi query; safety pass chỉ kích hoạt khi thật sự có thuật ngữ y khoa liên quan.",110,550,1060,28,{size:17,color:C.muted,align:"center"});
  notes(s,"40 giây. Dense và BM25 lấy candidate, RRF hợp nhất hạng, guideline pass thêm nguồn hướng dẫn vào pool, rồi BGE rerank. Sau ngưỡng điểm, OOD và bộ lọc, context có tối đa năm đoạn và có thể rỗng.",["E:\\project\\AcneLLM\\src\\acne_llm\\rag\\retriever.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\_retrieval.py","E:\\project\\AcneLLM\\src\\acne_llm\\rag\\reranker.py","E:\\project\\AcneLLM\\src\\acne_llm\\config.py"]);
}

// 15. Streaming, safety, persistence
{
  const s=deck.slides.add();header(s,"Sinh và hoàn tất","Câu trả lời chỉ hoàn tất sau hậu kiểm và lưu trạng thái",15);
  timeline(s,[["LỜI NHẮC","mẫu + hồ sơ + ngữ cảnh"],["PHÁT LUỒNG","Ollama token"],["CHUẨN HÓA","lọc CJK"],["NGUỒN","đoạn + siêu dữ liệu"],["AN TOÀN","hậu tố theo output thật"],["LƯU TRẠNG THÁI","SQLite + audit + done"]],272);
  const cards=[
    ["TIỀN TỐ KHẨN CẤP","có thể phát trước token khi route yêu cầu",C.wineP,C.wine],
    ["HẬU TỐ AN TOÀN","retinoid · thuốc kê đơn · liều · thủ thuật · khẩn cấp",C.wineP,C.wine],
    ["PHIÊN","lưu user + assistant turn, TTL mặc định 1.800 giây",C.navyP,C.navy],
    ["NHẬT KÝ","ghi route, model, retrieval và kết quả hoàn tất",C.grayP,C.navy],
  ];cards.forEach((v,i)=>{const x=56+(i%2)*594,y=430+Math.floor(i/2)*94;rect(s,x,y,550,72,{fill:v[2],line:v[3],lw:1.2});txt(s,v[0],x+20,y+18,150,22,{size:15,bold:true,color:v[3]});txt(s,v[1],x+184,y+15,340,42,{size:17,bold:true,align:"center"});});
  notes(s,"40 giây. Safety suffix dựa trên text model vừa sinh, facts và route flags, không chỉ dựa vào input. Sau đó runtime lưu user và assistant turn vào SQLite, ghi audit và phát done. Đây là tuyến cần eval production riêng.",["E:\\project\\AcneLLM\\src\\acne_llm\\chat\\runtime.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\_safety.py","E:\\project\\AcneLLM\\src\\acne_llm\\db\\session_store.py","E:\\project\\AcneLLM\\src\\acne_llm\\config.py"]);
}

// 16. Evaluation design
{
  const s=deck.slides.add();header(s,"Thiết kế kiểm định","v2_full đo ba tầng bằng ba giao thức khác nhau",16);
  metric(s,"1.490","Intaker single-turn",56,154,200,C.navy);metric(s,"120","retrieval cases",274,154,200,C.green);metric(s,"145 × 6","ablation rows: 870",492,154,216,C.ochre);metric(s,"13h42m","thời lượng toàn run",726,154,210,C.wine);metric(s,"OK","4 bước hoàn tất",954,154,270,C.green);
  const rows=[
    ["INTAKE","acne-intaker · no cache · no fallback","schema · intent · 11 fields · hallucination",C.navyP,C.navy],
    ["RETRIEVAL","hybrid thật · top 25 → rerank ≤ 5","relevance · precision · sufficiency · ranking",C.greenP,C.green],
    ["ABLATION","RRR/ORR/RNR/ROR/RRO/RNO","paired bootstrap 95% CI · judge gpt-5.6-luna",C.ochreP,C.ochre],
  ];rows.forEach((v,i)=>{const y=306+i*94;rect(s,56,y,1168,72,{fill:v[3],line:v[4],lw:1.2});txt(s,v[0],80,y+22,160,24,{size:17,bold:true,color:v[4]});txt(s,v[1],254,y+18,422,32,{size:18,bold:true});txt(s,v[2],700,y+18,494,34,{size:17,color:C.muted,align:"right"});});
  txt(s,"Generator: acne-generator-v2 · mô hình tham chiếu mạnh: gpt-5.6-terra · judge: gpt-5.6-luna",120,612,1040,24,{size:16,bold:true,align:"center"});
  txt(s,"145/145 mẫu Generator: synthetic_deepseek · synthetic_pending_review · deepseek-v4-pro",120,640,1040,22,{size:14,bold:true,color:C.wine,align:"center"});
  notes(s,"40 giây. v2_full hoàn tất intake, retrieval và ablation bằng ba protocol khác nhau. Toàn bộ 145 mẫu Generator là dữ liệu tổng hợp từ deepseek-v4-pro và đang chờ human review; đây là giới hạn của kết luận chất lượng.",["E:\\project\\AcneLLM\\research\\evaluation\\reports\\v2_full\\summary.json","E:\\project\\AcneLLM\\research\\evaluation\\reports\\v2_full\\intake\\report.json","E:\\project\\AcneLLM\\research\\evaluation\\reports\\v2_full\\retrieval\\results.json","E:\\project\\AcneLLM\\research\\evaluation\\reports\\v2_full\\ablation\\summary.json","E:\\project\\AcneLLM\\research\\evaluation\\datasets\\active\\generator_eval.v3_2_145.jsonl"]);
}

// 17. Intake eval
{
  const s=deck.slides.add();header(s,"Kết quả Intaker","Định tuyến mạnh; một số trường lâm sàng vẫn yếu",17);
  metric(s,"95,70%","intent accuracy",56,154,190,C.navy);metric(s,"0,7405","intent macro-F1",264,154,190,C.navy);metric(s,"98,12%","hợp lệ theo lược đồ",472,154,190,C.green);metric(s,"0,6131","extraction micro-F1",680,154,210,C.ochre);metric(s,"8,20%","hallucinated-field rate",908,154,316,C.wine);
  txt(s,"F1 theo trường được chọn",56,290,420,28,{size:23,bold:true,face:SERIF});const f=[["age",.9077],["skin",.9056],["lesion types",.8722],["products",.6897],["medications",.6341],["pregnancy",.5663],["sex",.5270],["allergies",.4762],["inflammation",.2126]];f.forEach((v,i)=>vbar(s,v[0],v[1],1,56,330+i*34,620,13,v[1]<.5?C.wine:(v[1]<.7?C.ochre:C.navy),v[1].toFixed(3)));
  rect(s,824,310,400,250,{fill:C.wineP,line:C.wine,lw:1.5});txt(s,"Kết luận",850,338,348,28,{size:23,bold:true,color:C.wine,face:SERIF});bullets(s,["0 parse failure, 0 fallback","28 schema violations","reject recall 0,9333","ưu tiên bổ sung inflammation, allergy, pregnancy, sex"],852,390,336,{size:18,gap:38,color:C.wine});
  txt(s,"N = 1.490; loại 10 multiturn. Trước loại: 1.410/1.500 intent advise; dữ liệu do deepseek-v4-pro sinh.",544,608,666,28,{size:14,color:C.muted,align:"right"});
  notes(s,"45 giây. Intent accuracy cao nhưng macro-F1 thấp hơn do lớp hiếm. Bộ dữ liệu tổng hợp bị lệch mạnh về advise: 1.410 trên 1.500 trước khi loại 10 multiturn. Các field inflammation, allergy và pregnancy là ưu tiên cải thiện.",["E:\\project\\AcneLLM\\research\\evaluation\\reports\\v2_full\\intake\\report.json","E:\\project\\AcneLLM\\research\\evaluation\\datasets\\active\\intake_eval.v2_1500.jsonl"]);
}

// 18. Retrieval eval
{
  const s=deck.slides.add();header(s,"Kết quả truy hồi","Xếp hạng tốt hơn độ bao phủ và chất lượng ngữ cảnh",18);
  const vals=[["Độ liên quan",2.5919,5,C.green],["Độ đầy đủ",2.8462,5,C.green],["Độ chính xác",.5344,1,C.ochre],["Chất lượng xếp hạng",.9365,1,C.navy]];vals.forEach((v,i)=>{const y=174+i*92;txt(s,v[0],56,y,250,26,{size:19,bold:true});rect(s,316,y+3,400,24,{fill:C.grayP,line:C.grayP,lw:0});rect(s,316,y+3,400*v[1]/v[2],24,{fill:v[3],line:v[3],lw:0});txt(s,`${v[1].toFixed(4)} / ${v[2]}`,730,y,110,26,{size:15,bold:true,color:v[3]});});
  rect(s,56,558,640,54,{fill:C.white,line:C.rule});txt(s,"120 cases",82,574,130,22,{size:17,bold:true});txt(s,"91 có context",248,574,170,22,{size:17,bold:true,color:C.green});txt(s,"29 no-context",454,574,194,22,{size:17,bold:true,color:C.wine});
  rect(s,856,168,368,386,{fill:C.greenP,line:C.green,lw:1.5});txt(s,"Diễn giải",880,196,320,28,{size:23,bold:true,color:C.green,face:SERIF});
  bullets(s,["Thứ tự context cuối có nDCG-judge 0,9365","liên quan 2,59/5; đầy đủ 2,85/5","độ chính xác 0,5344: ngữ cảnh chưa tập trung","29/120 câu không có ngữ cảnh","ưu tiên độ phủ trước khi chỉ tinh chỉnh bộ xếp hạng"],882,252,310,{size:17,gap:48,color:C.green});
  notes(s,"40 giây. Ranking quality 0,9365 là nDCG tính từ grade của LLM judge trên context cuối; đây là số đo cấp pipeline, không cô lập riêng BGE. Hai rubric relevance và sufficiency dùng thang 0–5. Nút thắt là độ phủ và độ tập trung của context.",["E:\\project\\AcneLLM\\research\\evaluation\\reports\\v2_full\\retrieval\\results.json","E:\\project\\AcneLLM\\research\\evaluation\\judges\\context.py"]);
}

// 19. Ablation
{
  const s=deck.slides.add();header(s,"Thí nghiệm loại bỏ (ablation)","Thay Generator tạo chênh lệch lớn nhất so với đường cơ sở cục bộ",19);
  txt(s,"Chất lượng câu trả lời trung bình / 5",56,150,430,28,{size:22,bold:true,face:SERIF});const arms=[["RRR",2.7793,C.navy],["ORR",2.7431,C.muted],["RNR",2.8966,C.muted],["ROR*",3.1100,C.ochre],["RRO",3.7379,C.green],["RNO",3.8069,C.wine]];arms.forEach((v,i)=>{const y=194+i*49;txt(s,v[0],56,y,64,22,{size:16,bold:true,color:v[2]});rect(s,126,y+2,500,20,{fill:C.grayP,line:C.grayP,lw:0});rect(s,126,y+2,500*v[1]/5,20,{fill:v[2],line:v[2],lw:0});txt(s,v[1].toFixed(3),640,y,74,22,{size:15,bold:true,color:v[2]});});
  txt(s,"Hiệu ứng ghép cặp so với RRR",760,150,464,28,{size:22,bold:true,face:SERIF});
  [["ROR",+.4118,"[0,2353; 0,5882]","n=68",C.ochre],["RRO",+.7248,"[0,5688; 0,8807]","n=109",C.green],["RNO",+.8214,"[0,6696; 0,9645]","n=112",C.wine],["RNR",+.0185,"[-0,0833; 0,1204]","n=108",C.muted],["ORR",-.0194,"[-0,1165; 0,0777]","n=103",C.muted]].forEach((v,i)=>{const y=194+i*49;txt(s,v[0],760,y,58,22,{size:16,bold:true,color:v[4]});txt(s,`${v[1]>=0?"+":""}${v[1].toFixed(4)}`,840,y,88,22,{size:17,bold:true,color:v[4]});txt(s,`CI 95% ${v[2]}`,940,y,196,22,{size:14,color:C.muted});txt(s,v[3],1142,y,72,22,{size:14,bold:true,color:v[4],align:"right"});});
  rect(s,56,504,1168,48,{fill:C.wineP,line:C.wine,lw:1.1});txt(s,"Lỗi an toàn thô: RRR 32 · ORR 24 · RNR 26 · ROR 18/100 · RRO 16 · RNO 13",76,517,1128,22,{size:16,bold:true,color:C.wine,align:"center"});
  rect(s,56,566,1168,64,{fill:C.white,line:C.rule});txt(s,"Ghép cặp loại hàng nếu một trong hai nhánh lỗi an toàn. ROR chỉ thành công 100/145; không lấy RRO − RNO làm hiệu ứng nhân quả riêng của RAG.",78,580,1124,38,{size:16,bold:true,color:C.muted,align:"center"});
  notes(s,"60 giây. Answer quality dùng rubric 1–5. ROR cũng có hiệu ứng ghép cặp dương 0,4118 trên 68 cặp. Phân tích paired loại hàng nếu một trong hai arm safety-fail, nên n khác nhau và các count safety phải đọc riêng. Không trừ RRO và RNO trực tiếp vì mỗi arm ghép với RRR trên tập hợp khác nhau.",["E:\\project\\AcneLLM\\research\\evaluation\\reports\\v2_full\\ablation\\summary.json","E:\\project\\AcneLLM\\research\\evaluation\\reports\\v2_full\\ablation\\rows.jsonl","E:\\project\\AcneLLM\\research\\evaluation\\judges\\rubrics.py"]);
}

// 20. Limitations
{
  const s=deck.slides.add();header(s,"Hạn chế và nguy cơ đối với tính hợp lệ","Bằng chứng chưa đủ cho tuyên bố lâm sàng hay vận hành thực tế",20);
  txt(s,"PHƯƠNG PHÁP VÀ DỮ LIỆU",56,150,550,24,{size:17,bold:true,color:C.wine});
  txt(s,"KỸ THUẬT VÀ TÁI LẬP",650,150,574,24,{size:17,bold:true,color:C.navy});
  const left=[
    ["01","Eval tổng hợp","145 mẫu Generator do deepseek-v4-pro sinh, đang chờ human review."],
    ["02","Thiếu đối chứng base","Chưa so với Qwen base; loss giảm không tự chứng minh fine-tune tốt hơn."],
    ["03","Judge chưa hiệu chuẩn","LLM judge chưa được hiệu chuẩn với bác sĩ và người dùng mục tiêu."],
    ["04","Lệch lớp / trường hiếm","Intake lệch advise; inflammation, allergy, pregnancy còn yếu."],
  ];
  const right=[
    ["05","Corpus Generator chưa đủ","Đã train 2.616 mẫu; corpus đạt 3.077/3.500 và còn 3 lỗi hậu kiểm."],
    ["06","Drift notebook / trạng thái","Notebook 2 epoch; trainer schedule 3; root adapter = checkpoint 300."],
    ["07","Chưa có eval T4/SSE","Ablation không đi qua stream, hậu tố safety và lưu SQLite."],
    ["08","Độ phủ và nhân quả","29/120 no-context; ghép cặp lọc lỗi safety; không suy RRO − RNO là hiệu ứng RAG."],
  ];
  [[left,56,C.wine],[right,650,C.navy]].forEach(group=>group[0].forEach((v,i)=>{const y=190+i*94;rule(s,group[1],y+78,550,C.rule,1);txt(s,v[0],group[1],y+8,42,24,{size:15,bold:true,color:group[2]});txt(s,v[1],group[1]+56,y+4,210,26,{size:17,bold:true,color:group[2]});txt(s,v[2],group[1]+278,y,272,62,{size:16});}));
  txt(s,"Giới hạn kết luận là một phần của kết quả khoa học, không phải phần phụ.",140,620,1000,28,{size:19,bold:true,color:C.wine,align:"center"});
  notes(s,"55 giây. Generator-v2 đã được fine-tune trên 2.616 mẫu train; hạn chế là corpus chưa đạt mục tiêu và chưa có đối chứng Qwen base. Toàn bộ tập Generator eval là synthetic pending review. Notebook và trainer state lệch nhau, deployment chưa khóa, còn ablation không bao phủ T4/SSE, safety suffix và persistence. Vì vậy kết quả có giá trị định vị nút thắt nhưng chưa chứng minh lâm sàng hay production.",["E:\\project\\AcneLLM\\.audit\\SLIDE_FACT_CHECK_2026-08-23.md","E:\\project\\AcneLLM\\model\\generator\\qwen25_acne_role_v2_lora\\checkpoint-450\\trainer_state.json","E:\\project\\AcneLLM\\research\\evaluation\\reports\\v2_full\\ablation\\summary.json","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\orchestrator.py","E:\\project\\AcneLLM\\src\\acne_llm\\chat\\runtime.py","E:\\project\\AcneLLM\\research\\evaluation\\runners\\run_ablation.py"]);
}

// 21. Roadmap
{
  const s=deck.slides.add();header(s,"Hướng phát triển","Mỗi thay đổi hành vi phải có một cổng kiểm định tương ứng",21);
  txt(s,"ƯU TIÊN",56,150,140,22,{size:13,bold:true,color:C.wine});txt(s,"HÀNH ĐỘNG",214,150,466,22,{size:13,bold:true,color:C.wine});txt(s,"CỔNG KIỂM ĐỊNH TRƯỚC KẾT LUẬN",714,150,510,22,{size:13,bold:true,color:C.wine});rule(s,56,180,1168,C.ink,1.2);
  const rows=[
    ["P0","Khóa manifest triển khai: đúng GGUF, model và prompt hash.","Chạy lại preflight + T3 + SSE trên chính gói triển khai."],
    ["P1","Hoàn tất corpus Generator và thêm đối chứng Qwen base.","Generator eval + paired ablation; không dùng loss thay quality."],
    ["P1","Bổ sung positives cho inflammation, allergy, pregnancy, medication.","Chạy lại intake 1.490; báo per-field và rare-value F1."],
    ["P2","Mở rộng nguồn mục tiêu và sửa 29 no-context cases.","Retrieval eval: coverage, relevance, precision, sufficiency, ranking."],
    ["P2","Tạo lane production T4/SSE: stream, suffix, persistence, latency.","Pass API E2E và phân biệt generator lỗi với hậu xử lý lỗi."],
    ["P3","Human-review tập synthetic và hiệu chuẩn judge bằng mẫu mù.","Báo agreement/bias trước khi dùng LLM score làm kết luận mạnh."],
  ];rows.forEach((v,i)=>{const y=198+i*70;txt(s,v[0],56,y+12,120,22,{size:17,bold:true,color:i===0?C.wine:C.navy});txt(s,v[1],214,y,454,54,{size:17,bold:i<2});txt(s,v[2],714,y,510,54,{size:16,color:C.muted});if(i<rows.length-1)rule(s,56,y+58,1168,C.rule,1);});
  rect(s,82,632,1116,34,{fill:C.navy,line:C.navy});txt(s,"Nguyên tắc: sửa tầng nào → chạy lại eval tầng đó; đường cơ sở cũ vẫn giữ làm bằng chứng lịch sử.",98,639,1084,20,{size:15,bold:true,color:C.white,align:"center"});
  notes(s,"45 giây. Roadmap bắt đầu bằng khóa model triển khai, sau đó hoàn tất corpus và thêm đối chứng base, cải thiện trường hiếm, độ phủ retrieval, T4/SSE và human calibration. Mỗi thay đổi hành vi có cổng kiểm định tương ứng.",["E:\\project\\AcneLLM\\.audit\\FUTURE_BEHAVIOR_ROADMAP.md","E:\\project\\AcneLLM\\.audit\\SAFE_REMEDIATION_TASKS.md","E:\\project\\AcneLLM\\.audit\\SLIDE_FACT_CHECK_2026-08-23.md"]);
}

// 22. Conclusion
{
  const s=deck.slides.add();header(s,"Kết luận","Pipeline nhất quán; gói triển khai và bằng chứng chưa khóa",22);
  const d=[
    ["DỮ LIỆU","KB 24.393 đoạn\nIntaker 4.000 cuối\nGenerator 3.077 đạt",C.greenP,C.green],
    ["MÔ HÌNH","3B cấu trúc hóa\n7B diễn đạt\nQLoRA + GGUF local",C.navyP,C.navy],
    ["RUNTIME","một UnifiedIntake\nRAG hybrid\nsafety + SQLite",C.grayP,C.navy],
    ["BẰNG CHỨNG","intent mạnh trên eval tổng hợp\nretrieval thiếu độ phủ\ngenerator là nút thắt lớn nhất",C.ochreP,C.ochre],
  ];d.forEach((v,i)=>{const x=56+i*296;rect(s,x,176,252,330,{fill:v[2],line:v[3],lw:2});txt(s,v[0],x+22,204,208,26,{size:17,bold:true,color:v[3],align:"center"});txt(s,v[1],x+26,278,200,126,{size:22,bold:true,face:SERIF,align:"center"});});
  rect(s,96,556,1088,76,{fill:C.ink,line:C.ink});txt(s,"Kết luận cuối",118,574,190,28,{size:22,bold:true,color:C.white,face:SERIF});txt(s,"Giá trị cốt lõi là chuỗi truy vết nguồn → model → runtime → eval; tiếp theo phải khóa gói deploy/eval và đối chứng base trước khi tối ưu.",324,568,834,44,{size:18,bold:true,color:C.white,align:"center"});
  notes(s,"25 giây. Pipeline runtime đã thống nhất về trách nhiệm, nhưng bằng chứng chưa khép kín vì model deploy mặc định khác model eval và chưa có đối chứng base. Thứ tự hợp lý là khóa parity, rồi cải thiện Generator, trường intake hiếm, retrieval và SSE.",["E:\\project\\AcneLLM\\.audit\\SLIDE_FACT_CHECK_2026-08-23.md","E:\\project\\AcneLLM\\docs\\ARCHITECTURE_TRUTH.md","E:\\project\\AcneLLM\\research\\evaluation\\reports\\v2_full\\summary.json"]);
}

async function writeBlob(file,blob){await fs.writeFile(file,new Uint8Array(await blob.arrayBuffer()));}
await fs.mkdir(RENDER,{recursive:true});
for(const [i,slide] of deck.slides.items.entries()){
  const stem=`slide-${String(i+1).padStart(2,"0")}`;
  await writeBlob(path.join(RENDER,`${stem}.png`),await deck.export({slide,format:"png",scale:1}));
  await fs.writeFile(path.join(RENDER,`${stem}.layout.json`),await (await slide.export({format:"layout"})).text());
}
await writeBlob(path.join(RENDER,"montage.webp"),await deck.export({format:"webp",montage:true,scale:1}));
await fs.writeFile(path.join(RENDER,"inspect.ndjson"),(await deck.inspect({kind:"slide,textbox,shape,notes",maxChars:100000})).ndjson);
const pptx=await PresentationFile.exportPptx(deck);await pptx.save(OUT);
console.log(`Created ${OUT} (${deck.slides.items.length} slides)`);
