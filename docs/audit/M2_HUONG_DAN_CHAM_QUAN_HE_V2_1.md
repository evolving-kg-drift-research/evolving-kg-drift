# Hướng dẫn chấm quan hệ M2 V3.1

**V2.1 · 11/11/2026 · Bản rà soát sau hiệu chuẩn**

Mỗi phiếu cần ghi nhãn quan hệ, kiểu của từng thực thể, lý do và đoạn quyết định khi có. Đọc bộ ba theo thứ tự **thực thể đầu → quan hệ → thực thể cuối**. Dùng đúng thân bài đã lưu của phiếu. Ba cách diễn giải cần chốt trước khi phát phiếu nằm ở mục 4.

## 1. Căn cứ cho quan hệ

| Nhãn | Căn cứ |
| --- | --- |
| **Hỗ trợ** | Bài xác lập đúng hai thực thể, quan hệ và vai trò của chúng trong phạm vi được hỏi. |
| **Không hỗ trợ** | Bài phủ định mệnh đề hoặc xác lập một thông tin mâu thuẫn với mệnh đề trong cùng bối cảnh. Dẫn nguyên văn phần bác bỏ và giải thích mâu thuẫn. |
| **Chưa đủ căn cứ** | Bài bỏ ngỏ mệnh đề, chỉ nêu dự kiến, hoặc nói về một sự kiện hay quan hệ khác. Ghi thông tin còn thiếu. |

Ví dụ, việc bài nêu một lần ra mắt sản phẩm B chỉ cho biết điều gì đã xảy ra với B. Để chấm *không hỗ trợ* cho mệnh đề phát hành A, cần thêm căn cứ bác bỏ mệnh đề về chính A, như câu nói rõ tổ chức chỉ phân phối A hoặc sự kiện được hỏi thuộc B và không bao gồm A. Với quan hệ `partners_with`, hai thứ tự thực thể biểu đạt cùng một quan hệ theo ontology.

| Quan hệ | Dấu hiệu cần tìm trong bài | Dấu hiệu riêng lẻ còn thiếu căn cứ |
| --- | --- | --- |
| `released_by` | Tổ chức ở cuối bộ ba đã phát hành, ra mắt hoặc đưa đúng đối tượng đầu ra cung cấp. Với linh kiện, xem cách xử lý đề xuất ở mục 4. | Sở hữu, thiết kế, thử nghiệm, bảng giá hoặc ra mắt thiết bị chủ. |
| `succeeded_by` | Bài xác định thực thể cuối kế nhiệm hoặc thay thế thực thể đầu trong đúng dòng hoặc vai trò. Xem ca thế hệ công nghệ ở mục 4. | Hai đối tượng xuất hiện theo thứ tự thời gian hoặc được nhắc trong cùng lộ trình. |
| `based_on` | Bài mô tả thực thể đầu được xây dựng, phát triển hoặc thiết kế dựa trên thực thể cuối. | Tương thích, kết nối, hoặc hai đối tượng được nhắc cạnh nhau. |
| `invested_in` | Bài xác nhận thực thể đầu đã đầu tư vào thực thể cuối, kể cả khi cùng đầu tư với các bên khác. | Đàm phán, cân nhắc đầu tư, hoặc thông báo gọi vốn chỉ nêu số tiền. |
| `acquired_by` | Bài xác nhận thực thể cuối đã mua lại thực thể đầu. | Tin đồn, đề nghị mua hoặc thương vụ còn chờ hoàn tất. |
| `version_of` | Bài xác định thực thể đầu là phiên bản hoặc biến thể của thực thể cuối. | Tên tương tự, thứ tự ra mắt hoặc cùng hãng. |
| `integrated_into` | Bài xác nhận thực thể đầu đã được đưa vào sản phẩm, phần mềm hoặc nền tảng ở cuối bộ ba. | Dự định tích hợp, hoặc có thể kết nối mà chưa rõ thành phần đã được đưa vào. |
| `partners_with` | Bài xác lập hai thực thể là các bên hợp tác trong hoạt động được nêu. | Xuất hiện cùng một sự kiện hoặc cùng được trích dẫn. |
| `works_at` | Bài xác định người ở đầu làm việc tại tổ chức ở cuối trong thời gian được mô tả. | Phát biểu tại sự kiện của tổ chức, hoặc được tổ chức trích dẫn. |
| `is_CEO_of` | Bài xác định người ở đầu giữ chức CEO của đúng tổ chức ở cuối trong thời gian được mô tả. | Chức danh quản lý khác, hoặc thông báo bổ nhiệm cho thời điểm chưa có hiệu lực. |

Các dấu hiệu trên giúp đọc đúng mệnh đề và chiều quan hệ. Cách diễn đạt tương đương được chấp nhận khi ngữ cảnh xác lập đủ căn cứ. [Ontology 1.1](../../config/ontology.yaml)

## 2. Kiểu của hai thực thể

Trước hết xác định đối tượng mà tên trong bài chỉ tới. Sau đó đối chiếu kiểu của đối tượng đầu và cuối với các kiểu cho phép ở từng vai trò trong ontology 1.1. Ghi căn cứ cho cả hai. Kết quả về kiểu và nhãn quan hệ có thể khác nhau, như câu xác nhận một người kế nhiệm người khác dù `succeeded_by` trong ontology áp dụng cho mô hình AI, sản phẩm và phần mềm.

- **Đúng kiểu** khi cả hai kiểu có căn cứ và đều được phép.
- **Sai kiểu** khi có căn cứ xác định ít nhất một kiểu nằm ngoài phạm vi. Ghi rõ tên kiểu đã xác minh hoặc loại đối tượng nằm ngoài danh mục.
- **Chưa xác minh kiểu** khi còn ít nhất một kiểu thiếu căn cứ và chưa xác định được kiểu nào sai. Nếu bài dùng một tên cho cả mô hình và ứng dụng mà đoạn đang xét chưa làm rõ đối tượng, ghi các cách hiểu trong lý do.

Với `Product`, cần nhận diện đối tượng cụ thể trong bài, chẳng hạn tên sản phẩm, mã chip, dòng chip hoặc kiến trúc tập lệnh. Khi hồ sơ kiểu đã xác minh có ghi đúng đối tượng, dẫn nguồn hồ sơ và đối chiếu cách bài dùng tên. Khi căn cứ chỉ là bài gọi tên đối tượng phần cứng, áp dụng cách diễn giải ở mục 4 sau khi được chốt. Hiệu lực của ánh xạ thực thể theo mốc cắt là một kiểm tra riêng. [Danh sách kiểu và phạm vi quan hệ](../../config/ontology.yaml)

## 3. Đoạn quyết định và đoạn lặp

Với *hỗ trợ* hoặc *không hỗ trợ*, chọn đoạn liên tục ngắn nhất đủ hiểu thực thể, vai trò và căn cứ. Mở rộng sang câu liền kề khi cần xác định tên, đại từ hoặc trạng thái của sự kiện. Với *chưa đủ căn cứ*, ghi điều còn thiếu và để trống đoạn quyết định.

Nếu nguyên văn xuất hiện nhiều lần trong cùng thân bài, xét ngữ cảnh của từng lần. Chọn lần có vị trí bắt đầu nhỏ nhất trong các lần có ngữ cảnh đủ căn cứ tương đương. Nếu lần đầu cần thêm câu để giải nghĩa, chọn đoạn liên tục đủ căn cứ rồi mới so sánh với các vị trí tương đương. Ghi khoảng `[bắt đầu, kết thúc)` tính theo điểm mã Unicode từ đầu thân bài. Xếp đoạn đã chọn vào đoạn gốc, ngữ cảnh liền kề hoặc đoạn khác trong cùng bản lưu theo vị trí thực tế.

Trong ca Exynos, đoạn người phân xử đã chọn xuất hiện tại ba vị trí bắt đầu 1118, 1634 và 2150. Đây là ví dụ kiểm tra cách ghi vị trí. Khi dùng đoạn dẫn cho một snapshot, xác minh nguyên văn, mã băm đoạn, mã băm thân bài và mốc quan sát của đúng bản lưu chứa đoạn. Mốc quan sát phải không muộn hơn mốc cắt của snapshot. [Biên nhận hiệu chuẩn](../../outputs/m2_anchor_semantic_review/20261111_tiep_nhan_hieu_chuan_v2/bien_nhan_kiem_tra.json)

## 4. Ba cách diễn giải đề xuất để chốt

| Vấn đề | Đề xuất để người phụ trách xác nhận | Ca cần xem lại theo cách diễn giải được chốt |
| --- | --- | --- |
| **Phát hành linh kiện cùng thiết bị** | Chấp nhận sự kiện chung khi bài xác lập linh kiện cụ thể cũng được ra mắt hoặc đưa ra cung cấp bởi đúng tổ chức. Khi bài chỉ xác nhận thiết bị ra mắt, dùng linh kiện đó và công bố thông số, ghi *chưa đủ căn cứ* cho sự kiện phát hành linh kiện. | Exynos 2600 và Galaxy S26. Người phân xử đã chấm *hỗ trợ* với mức chắc chắn trung bình. |
| **Thứ tự thế hệ và kế nhiệm** | Yêu cầu bài xác lập vai trò kế nhiệm hoặc thay thế thực sự của B đối với A. Khi câu chỉ nói B là thế hệ sau A và quá trình chuyển tiếp còn ở dạng dự kiến, ghi *chưa đủ căn cứ*. Đánh giá kiểu của A và B riêng. | 5G–6G. Người phân xử đã chấm *hỗ trợ* về nghĩa thông thường và *sai kiểu* theo ontology. |
| **Chip và dòng chip trong kiểu Product** | Cho phép chọn `Product` khi bài hoặc hồ sơ kiểu đã xác minh nhận diện rõ một chip hoặc dòng chip có tên như một sản phẩm phần cứng cụ thể. Khi tên chỉ một kiến trúc tập lệnh, ghi loại đối tượng đã xác định và đối chiếu phạm vi kiểu. Khi thiếu căn cứ phân biệt kiến trúc với sản phẩm cụ thể, ghi *chưa xác minh kiểu*. | Exynos 2600, dòng M và 3A6000 là các ca cần xác nhận cách dùng `Product`. Kiến trúc ARM và LoongArch là các ca đối chiếu vai trò ở cuối quan hệ `based_on`. |

Ba cách diễn giải này có thể đổi cách chấm một ca. Sau khi chốt, người phân xử chỉ cần rà lại các quyết định bị ảnh hưởng và ghi căn cứ bổ sung. Đối với hai ca đầu tư, đoạn ở chỗ khác trong thân bài giúp xác định đúng bên đầu tư và bên nhận đầu tư. Đối với Claude, Mythos 5 và DeepSeek-Chat, có thể dùng lại lý do đã ghi để minh họa căn cứ còn thiếu cho `released_by`. [Hồ sơ 10 ca đã chấm](../../outputs/m2_anchor_semantic_review/20261111_tiep_nhan_hieu_chuan_v2/bien_nhan_kiem_tra.json)

## 5. Ví dụ cho hai nhánh chưa xuất hiện trong 10 ca

| Nhánh | Ví dụ giả định dùng để tập chấm | Cách ghi |
| --- | --- | --- |
| **Không hỗ trợ** | Bộ ba đề xuất `X → released_by → Y`. Bài nêu rõ Y chỉ phân phối X và chính Z phát hành X. | Chọn *không hỗ trợ*. Dẫn câu xác định vai trò của Y và Z đối với đúng X. |
| **Chưa xác minh kiểu** | Bộ ba đề xuất `Orion → released_by → Công ty A`. Bài xác nhận A đã phát hành Orion và chỉ mô tả Orion là một dự án, chưa có chi tiết xác định đó là mô hình, phần mềm hay sản phẩm cụ thể. | Chọn *hỗ trợ* về sự kiện nếu đoạn xác lập rõ việc phát hành. Ghi *chưa xác minh* cho kiểu Orion và giữ kiểu tổ chức của A nếu bài xác lập rõ. |

Hai ví dụ giả định dùng để thống nhất cách ghi nhãn trong buổi hiệu chuẩn. Báo cáo mức đồng thuận của lượt chấm độc lập dùng quyết định trên phiếu thật của lượt đó.
