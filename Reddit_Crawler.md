# Reddit Crawler

Backend FastAPI để crawl bài viết Reddit, lưu source, post, comment, metric và job vào SQLite theo schema có sẵn trong `data/schema_table_reddit.sql`.

Database hiện tại là contract chính của dự án. Code không tự ý thêm, xóa hoặc đổi tên bảng/cột và mặc định sử dụng `data/reddit.db`.

## Mục Tiêu

- Theo dõi các bài viết mới được đăng trong cửa sổ `LOOKBACK_HOURS`, mặc định 24 giờ.
- Hỗ trợ source theo `subreddit`, `keyword`, `user` và `latest`.
- Upsert bài viết theo `reddit_post_id`.
- Theo dõi mức độ thảo luận bằng `score` và `comments_count`.
- Lưu lịch sử metric vào `post_metrics`.
- Chỉ lưu nội dung comment khi source có `include_comments=true`.
- Scheduler tự động crawl source và cập nhật metric cho post đến hạn.
- Không thay đổi schema hiện tại trong quá trình khởi tạo code.

## Chức Năng Chính

- Tạo và quản lý source Reddit.
- Crawl bài mới trong vòng 24 giờ gần nhất.
- Upsert post theo `reddit_post_id`.
- Lưu mapping nhiều-nhiều source–post trong `source_posts`.
- Theo dõi các metric:
  - `score`
  - `comments_count`
- Lưu snapshot metric vào `post_metrics`.
- Crawl comment khi source bật `include_comments=true`.
- Lưu trạng thái từng lần chạy vào `pipeline_jobs`.
- Ghi lỗi quan trọng vào `pipeline_logs`.
- Tính `schedule_tier` cho source và `metric_tier` cho post.
- API để quản lý source, post, comment, metric và job.
- Hỗ trợ chạy scrape và update metric thủ công.

## Stack

- FastAPI
- SQLAlchemy 2.x
- Pydantic 2.x
- SQLite
- requests
- browser-cookie3
- python-dotenv
- pytest
- httpx

Không thêm Playwright, Selenium hoặc PRAW vào core ban đầu nếu chưa thực sự cần.

## Cài Đặt

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Ví dụ `requirements.txt`:

```text
fastapi
uvicorn
sqlalchemy
pydantic
pydantic-settings
requests
browser-cookie3
python-dotenv
pytest
httpx
```

## Biến Môi Trường

Tạo file `.env`:

```env
DATABASE_URL="sqlite:///./data/reddit.db"

LOOKBACK_HOURS=24
REQUEST_TIMEOUT_SECONDS=30
MAX_POSTS_PER_SOURCE=100

COOKIE_CACHE_TTL_SECONDS=43200
REDDIT_USER_AGENT="linux:reddit-crawler:v1.0"
```

Biến môi trường trên hệ điều hành được ưu tiên hơn giá trị trong `.env`.

Không lưu cookie trực tiếp trong `.env`.

## Cookie Cache

Crawler hiện tại có thể lấy cookie Reddit từ trình duyệt đã đăng nhập bằng `browser-cookie3`.

Cookie được cache trong file riêng:

```text
.reddit_cookies_cache.json
```

File này chỉ là session cache, không thuộc database và không được commit lên Git.

Thêm vào `.gitignore`:

```gitignore
.env
venv/
__pycache__/
*.pyc
data/*.db
.reddit_cookies_cache.json
```

Quy tắc cookie:

1. Thử đọc cache nếu cache còn hạn.
2. Nếu cache hết hạn hoặc request bị từ chối, thử đọc cookie mới từ trình duyệt.
3. Thứ tự trình duyệt:
   - Chrome
   - Edge
   - Brave
   - Firefox
4. Ghi lại cookie mới vào cache.
5. Nếu tất cả trình duyệt đều thất bại, trả lỗi rõ ràng; không tạo dữ liệu giả.
6. Không log toàn bộ cookie hoặc giá trị session nhạy cảm.

Ví dụ cấu hình:

```python
COOKIE_CACHE_TTL_SECONDS = 12 * 60 * 60

BROWSER_LOADERS = [
    ("chrome", browser_cookie3.chrome),
    ("edge", browser_cookie3.edge),
    ("brave", browser_cookie3.brave),
    ("firefox", browser_cookie3.firefox),
]
```

## Chạy App

```bash
uvicorn app.main:app --reload
```

## Loại Source

`sources.source_type` hỗ trợ đúng 4 kiểu theo schema:

```text
subreddit
keyword
user
latest
```

### 1. Subreddit

Theo dõi bài mới trong một subreddit.

Ví dụ identifier:

```text
vozforums
python
programming
```

URL listing:

```text
https://www.reddit.com/r/vozforums/new.json?limit=100
```

HTML tương ứng:

```text
https://www.reddit.com/r/vozforums/new/
```

Khi lưu `identifier`, chỉ lưu tên subreddit:

```text
vozforums
```

Không lưu `r/vozforums` hoặc URL đầy đủ.

### 2. Keyword

Tìm bài Reddit theo từ khóa.

Ví dụ identifier:

```text
memory leak
playwright
database locked
```

URL JSON:

```text
https://www.reddit.com/search.json?q=memory%20leak&sort=new&limit=100
```

HTML tương ứng:

```text
https://www.reddit.com/search/?q=memory%20leak&sort=new
```

### 3. User

Theo dõi các bài viết mới của một Reddit user.

Ví dụ identifier:

```text
spez
kisuke_urahara23
```

URL JSON:

```text
https://www.reddit.com/user/spez/submitted.json?sort=new&limit=100
```

HTML tương ứng:

```text
https://www.reddit.com/user/spez/submitted/
```

Khi lưu `identifier`, chỉ lưu username, không thêm `u/`.

### 4. Latest

Theo dõi bài mới toàn Reddit.

Identifier cố định:

```text
all
```

URL JSON:

```text
https://www.reddit.com/r/all/new.json?limit=100
```

HTML tương ứng:

```text
https://www.reddit.com/r/all/new/
```

## API Backend

- `GET /health`: kiểm tra trạng thái ứng dụng và kết nối database.
- `POST /sources`: tạo source mới và có thể scrape ngay.
- `GET /sources`: lấy danh sách source.
- `GET /sources/{source_id}`: xem chi tiết source.
- `PATCH /sources/{source_id}`: cập nhật cấu hình source.
- `DELETE /sources/{source_id}`: vô hiệu hóa hoặc xóa source theo thiết kế service.
- `POST /sources/{source_id}/scrape`: scrape thủ công một source.
- `GET /posts`: lấy danh sách post.
- `GET /posts/{post_id}`: xem chi tiết post.
- `GET /comments`: lấy danh sách comment đã lưu.
- `GET /comments/{comment_id}`: xem chi tiết comment.
- `POST /metrics/due/run`: update metric cho các post đã đến hạn.
- `POST /scheduler/run-due`: chạy source và post đang đến hạn.
- `GET /jobs`: lấy danh sách pipeline job.
- `GET /jobs/{job_id}`: xem chi tiết một job.
- `GET /logs`: lấy danh sách pipeline log.

Không tạo endpoint cho bảng hoặc tính năng không tồn tại trong schema.

## Ví Dụ Tạo Source Theo Subreddit

```bash
curl -X POST http://127.0.0.1:8000/sources   -H "Content-Type: application/json"   -d '{
    "source_type": "subreddit",
    "identifier": "vozforums",
    "include_comments": false
  }'
```

## Ví Dụ Tạo Source Theo Keyword

```bash
curl -X POST http://127.0.0.1:8000/sources   -H "Content-Type: application/json"   -d '{
    "source_type": "keyword",
    "identifier": "memory leak",
    "include_comments": false
  }'
```

## Ví Dụ Tạo Source Theo User

```bash
curl -X POST http://127.0.0.1:8000/sources   -H "Content-Type: application/json"   -d '{
    "source_type": "user",
    "identifier": "spez",
    "include_comments": false
  }'
```

## Ví Dụ Tạo Source Latest

```bash
curl -X POST http://127.0.0.1:8000/sources   -H "Content-Type: application/json"   -d '{
    "source_type": "latest",
    "identifier": "all",
    "include_comments": false
  }'
```

## Quy Tắc Crawl Bài Mới

Crawler lấy tối đa `MAX_POSTS_PER_SOURCE` bài mới, sau đó chỉ giữ các bài có:

```text
post_created_at >= now - LOOKBACK_HOURS
```

Mặc định:

```text
LOOKBACK_HOURS = 24
MAX_POSTS_PER_SOURCE = 100
```

Listing Reddit được sắp xếp mới nhất trước. Khi gặp bài cũ hơn cutoff, crawler có thể dừng vòng lặp.

Crawler không dựa vào thời gian nhận dữ liệu để xác định bài mới; phải dùng trường `created_utc` của Reddit.

## Cấu Trúc Response Listing

Response listing Reddit thường có dạng:

```json
{
  "kind": "Listing",
  "data": {
    "after": "t3_xxxxx",
    "before": null,
    "children": [
      {
        "kind": "t3",
        "data": {
          "id": "1uwtr0e",
          "name": "t3_1uwtr0e",
          "title": "Example title",
          "created_utc": 1784000000,
          "score": 2,
          "upvote_ratio": 1.0,
          "num_comments": 0
        }
      }
    ]
  }
}
```

Dữ liệu post thật nằm trong:

```python
payload["data"]["children"][index]["data"]
```

Không dùng `kind` hoặc wrapper listing làm dữ liệu post.

## Mapping Dữ Liệu Vào Bảng `posts`

| Reddit JSON | Database |
|---|---|
| `id` | `reddit_post_id` |
| `subreddit` | `subreddit_name` |
| `title` | `title` |
| `permalink` | `permalink` |
| `url` | `external_url` |
| `author` | `author_name` |
| `author_fullname` | `author_fullname` |
| `selftext` | `selftext` |
| `link_flair_text` | `link_flair_text` |
| `is_self` | `is_self` |
| `over_18` | `is_nsfw` |
| `stickied` | `is_stickied` |
| `locked` | `is_locked` |
| `created_utc` | `post_created_at` |

`permalink` từ Reddit thường là path tương đối. Trước khi lưu, chuẩn hóa thành URL đầy đủ:

```text
https://www.reddit.com + permalink
```

Ví dụ:

```text
https://www.reddit.com/r/vozforums/comments/1uwtr0e/example_title/
```

### `post_type`

Xác định `post_type` theo thứ tự ưu tiên:

```text
text
link
image
video
gallery
poll
other
```

Quy tắc gợi ý:

- `is_self=true` → `text`
- `is_gallery=true` → `gallery`
- `is_video=true` hoặc `post_hint=hosted:video` → `video`
- `post_hint=image` → `image`
- URL ngoài Reddit → `link`
- Không xác định được → `other`

Không tự tạo thêm giá trị ngoài CHECK constraint của schema.

## Mapping Metric

| Reddit JSON | Database |
|---|---|
| `score` | `post_metrics.score` |
| `num_comments` | `post_metrics.comments_count` |

Ý nghĩa:

- `score`: điểm vote ròng gần đúng do Reddit trả về; không phải tổng upvote tuyệt đối.
- `comments_count`: tổng số comment được Reddit báo cáo.

Không tạo hoặc ước lượng trường `upvote_count`. Reddit không cung cấp số upvote tuyệt đối đáng tin cậy.

Mỗi lần crawl mới hoặc update metric thành công:

1. Cập nhật `posts.last_metric_update`.
2. Ghi một snapshot mới vào `post_metrics`.
3. Tính lại `metric_tier`.
4. Tính `posts.next_metric_update`.

Không update ngược snapshot cũ.

## Mapping Comment

| Reddit JSON | Database |
|---|---|
| `id` | `reddit_comment_id` |
| `parent_id` | `parent_reddit_id` |
| `author` | `author_name` |
| `author_fullname` | `author_fullname` |
| `body` | `body` |
| `score` | `score` |
| `depth` | `depth` |
| `is_submitter` | `is_submitter` |
| `stickied` | `is_stickied` |
| `created_utc` | `comment_created_at` |

Ý nghĩa:

- `parent_reddit_id`: fullname của parent, thường bắt đầu bằng `t1_` với comment hoặc `t3_` với post.
- `is_submitter=true`: comment do tác giả của post viết.
- `is_stickied=true`: comment được moderator ghim.
- `author_fullname`: ID nội bộ Reddit của user, thường bắt đầu bằng `t2_`.

Nếu dữ liệu không cung cấp `author_fullname`, lưu `NULL`.

Nếu comment đã bị xóa:

```text
author_name = NULL
body = NULL hoặc "[deleted]" tùy dữ liệu nguồn
is_deleted = true
```

Không suy đoán username đã bị xóa.

## Database

Schema hiện có gồm đúng các bảng:

- `sources`
- `posts`
- `source_posts`
- `analytics_cache`
- `pipeline_jobs`
- `post_metrics`
- `comments`
- `pipeline_logs`

### `sources`

Lưu cấu hình source và lịch crawl.

Các trường quan trọng:

- `source_type`
- `identifier`
- `is_active`
- `is_accessible`
- `include_comments`
- `last_scraped`
- `next_scrape`
- `schedule_tier`
- `schedule_override_minutes`

Unique theo:

```text
(source_type, identifier)
```

### `posts`

Lưu thông tin hiện tại của post và lịch update metric.

`id` là khóa chính nội bộ của database.

`reddit_post_id` là ID thật từ Reddit, ví dụ:

```text
1uwtr0e
```

Không lưu fullname `t3_1uwtr0e` vào `reddit_post_id`.

Một post có thể có `source_id` gốc, nhưng quan hệ nhiều source phải được lưu trong `source_posts`.

### `source_posts`

Một post có thể được tìm thấy từ nhiều source khác nhau.

Ví dụ một post có thể đồng thời:

- thuộc subreddit `python`;
- khớp keyword `playwright`;
- được tìm thấy trong source `latest`.

Khi gặp lại mapping đã tồn tại:

```text
giữ nguyên first_seen_at
cập nhật last_seen_at
```

### `post_metrics`

Lưu lịch sử metric theo từng lần cập nhật:

- `score`
- `comments_count`
- `recorded_at`
- `job_id`

Bảng này là lịch sử append-only.

### `comments`

Chỉ ghi khi source liên quan có:

```text
include_comments = true
```

Upsert comment theo:

```text
reddit_comment_id
```

Nếu chỉ cần theo dõi độ thảo luận, để `include_comments=false` và sử dụng `comments_count` từ `post_metrics`.

### `analytics_cache`

Lưu thống kê theo ngày của từng source:

- `total_posts`
- `total_comments`
- `total_score`
- `avg_comments_per_post`
- `avg_score_per_post`
- `top_post_id`
- `growth_rate`

Công thức:

```text
avg_comments_per_post =
total_comments / total_posts
```

```text
avg_score_per_post =
total_score / total_posts
```

Nếu `total_posts = 0`, hai giá trị trung bình bằng `0`.

Công thức growth:

```text
growth_rate =
(current_total_posts - previous_total_posts)
/
previous_total_posts
```

Nếu ngày trước không có dữ liệu hoặc `previous_total_posts = 0`, đặt `growth_rate = 0`.

`top_post_id` chọn post có mức độ thảo luận cao nhất trong source/ngày. Ưu tiên:

```text
comments_count DESC
score DESC
```

### `pipeline_jobs`

Ghi trạng thái của từng operation.

`job_type` chỉ dùng các giá trị trong schema:

```text
scrape_posts
scrape_new_posts
update_metrics
scrape_comments
```

Counters:

- `posts_found`: số post đọc được từ nguồn.
- `posts_new`: số post mới insert.
- `posts_updated`: số post hiện có được cập nhật.
- `items_failed`: số item xử lý thất bại.

Nếu một post lỗi nhưng các post khác vẫn thành công:

- tăng `items_failed`;
- tiếp tục xử lý các post còn lại;
- ghi lỗi vào `pipeline_logs`;
- job chỉ `failed` nếu operation tổng thể không thể hoàn thành.

### `pipeline_logs`

Chỉ lưu lỗi hoặc cảnh báo quan trọng.

`log_level` chỉ nhận:

```text
ERROR
WARNING
```

Không lưu log `INFO` vào database.

Không ghi cookie, authorization header hoặc dữ liệu nhạy cảm vào `error_details`.

## Metric Tier Cho Post

Tính tier dựa trên `comments_count` và `score`.

Công thức ban đầu:

```python
engagement = comments_count * 5 + max(score, 0) * 2
```

Ngưỡng gợi ý:

```python
if engagement >= 100:
    return "hot"
if engagement >= 50:
    return "high"
if engagement >= 20:
    return "medium"
if engagement >= 5:
    return "low"
return "very_low"
```


Các ngưỡng phải đặt trong config hoặc một module riêng để dễ điều chỉnh, không hard-code rải rác.

## Lịch Update Metric

Post chỉ được theo dõi trong `LOOKBACK_HOURS`, mặc định 24 giờ.

Khi tạo post:

```text
tracking_until = post_created_at + LOOKBACK_HOURS
is_tracked = true
```

Khi `now >= tracking_until`:

```text
is_tracked = false
next_metric_update = NULL
```

Khoảng thời gian gợi ý:

```python
minutes_by_tier = {
    "hot": 30,
    "high": 90,
    "medium": 240,
    "low": 360,
    "very_low": 720,
}
```

Nếu thời điểm update tiếp theo vượt `tracking_until`, đặt:

```text
next_metric_update = tracking_until
```

Sau lần update cuối tại hoặc sau `tracking_until`, dừng theo dõi.

## Schedule Tier Cho Source

`analytics_cache` là nguồn dữ liệu để ước lượng độ hoạt động của source.

Có thể dùng:

```python
activity_score = (
    total_posts * 5
    + total_comments * 2
    + max(total_score, 0)
)
```

Tier 1 là source hoạt động mạnh nhất, tier 5 là yếu nhất.

Ngưỡng ban đầu:

```python
if activity_score >= 1000:
    schedule_tier = 1
elif activity_score >= 500:
    schedule_tier = 2
elif activity_score >= 200:
    schedule_tier = 3
elif activity_score >= 50:
    schedule_tier = 4
else:
    schedule_tier = 5
```

Thời gian crawl source gợi ý:

```python
minutes_by_schedule_tier = {
    1: 30,
    2: 60,
    3: 120,
    4: 240,
    5: 360,
}
```

Nếu `schedule_override_minutes` khác `NULL`, luôn ưu tiên giá trị override.

## Scheduler

Scheduler định kỳ kiểm tra:

- Source có:
  ```text
  is_active = true
  is_accessible = true
  next_scrape <= now
  ```
- Post có:
  ```text
  is_tracked = true
  next_metric_update <= now
  ```

Scheduler dùng một vòng quét trung tâm. Không tạo một scheduler riêng cho từng source hoặc từng post.

### Khi Source Đến Hạn

1. Tạo `pipeline_job` với `job_type=scrape_new_posts`.
2. Đặt job thành `running`.
3. Gọi Reddit listing tương ứng với source.
4. Lọc post trong `LOOKBACK_HOURS`.
5. Upsert post.
6. Upsert mapping `source_posts`.
7. Ghi snapshot `post_metrics`.
8. Nếu `include_comments=true`, crawl comment cho post mới.
9. Cập nhật counters của job.
10. Cập nhật `sources.last_scraped`.
11. Tính lại `schedule_tier`.
12. Tính `sources.next_scrape`.
13. Đặt job thành `done`.

Nếu source bị từ chối truy cập:

```text
is_accessible = false
```

Chỉ đặt như vậy khi lỗi cho thấy source thực sự không thể truy cập, không phải lỗi mạng tạm thời.

### Khi Post Đến Hạn Update Metric

1. Chỉ tạo job `update_metrics` khi có post đến hạn.
2. Gọi endpoint theo `reddit_post_id` hoặc permalink.
3. Cập nhật dữ liệu hiện tại trong `posts` nếu cần.
4. Ghi snapshot mới vào `post_metrics`.
5. Tính lại `metric_tier`.
6. Tính `next_metric_update`.
7. Nếu hết `tracking_until`, đặt `is_tracked=false`.
8. Nếu update một post lỗi:
   - tăng `items_failed`;
   - ghi `pipeline_logs`;
   - tiếp tục post tiếp theo.

## Reddit Client

Tạo service riêng:

```text
app/services/reddit_client.py
```

Trách nhiệm:

- Build URL theo loại source.
- Tải và cache cookie.
- Gửi HTTP request với timeout.
- Parse JSON.
- Kiểm tra response thực sự là JSON.
- Phân biệt lỗi HTTP, block page, login page và JSON lỗi.
- Trả dữ liệu thuần cho service layer.
- Không ghi trực tiếp database.

Headers tối thiểu:

```python
{
    "User-Agent": settings.REDDIT_USER_AGENT,
    "Accept": "application/json,text/plain,*/*",
}
```

Không hard-code cookie trong source code.

## Xử Lý Response Và Lỗi

Trước khi gọi `response.json()`, phải kiểm tra:

```text
HTTP status
Content-Type
nội dung đầu response nếu nghi ngờ HTML block page
```

Các trường hợp cần xử lý:

- `200` + JSON hợp lệ: thành công.
- `200` + HTML login/block page: thất bại, không coi là JSON success.
- `401`: session không hợp lệ.
- `403`: bị từ chối hoặc network security block.
- `404`: source/post không còn tồn tại.
- `429`: rate limited.
- timeout/network error: lỗi tạm thời.

Khi `429`, dùng `Retry-After` nếu response có.

Không retry vô hạn. Số lần retry phải có giới hạn và có backoff.

## Không Dùng RSS Làm Nguồn Metric Chính

RSS có thể dùng làm fallback để phát hiện post mới:

```text
https://www.reddit.com/r/vozforums/new.rss
```

Nhưng RSS thường thiếu:

- `score`
- `upvote_ratio`
- `num_comments`
- cấu trúc comment đầy đủ

Vì vậy:

```text
RSS = fallback phát hiện post
JSON = nguồn dữ liệu chính
```

Nếu dùng RSS fallback, metric thiếu phải lưu `NULL` hoặc chờ lần update sau; không tự đặt số giả.

## Cấu Trúc Thư Mục

```text
app/
  main.py

  core/
    config.py
    constants.py

  db/
    session.py
    models.py
    schemas.py

  api/
    sources.py
    posts.py
    comments.py
    metrics.py
    jobs.py
    logs.py
    scheduler.py

  repositories/
    source_repository.py
    post_repository.py
    comment_repository.py
    metric_repository.py
    analytics_repository.py
    job_repository.py
    log_repository.py

  services/
    reddit_client.py
    cookie_service.py
    source_service.py
    post_service.py
    comment_service.py
    metric_service.py
    analytics_service.py
    scheduler_service.py

tests/
  test_sources_api.py
  test_posts_api.py
  test_metric_service.py
  test_scheduler_service.py
  test_reddit_client.py

test_crawl_data/
  test_crawl_subreddit.py
  test_crawl_keyword.py
  test_crawl_user.py
  test_update_post_metrics.py
  test_crawl_comments.py

data/
  reddit.db
  schema_table_reddit.sql

.reddit_cookies_cache.json
.env
.gitignore
requirements.txt
```

Không tạo package hoặc abstraction không cần thiết ngoài cấu trúc trên.

## Nguyên Tắc Repository Và Service

- API layer chỉ nhận request và trả response.
- Service layer chứa nghiệp vụ.
- Repository layer chỉ truy cập database.
- Reddit client chỉ gọi nguồn bên ngoài.
- Không để route gọi SQLAlchemy trực tiếp.
- Không để repository tự gọi Reddit.
- Mỗi transaction phải rõ ràng; rollback khi lỗi.
- Dùng type hints đầy đủ cho public function.
- Không dùng broad `except Exception` nếu có thể bắt lỗi cụ thể.
- Không bỏ qua lỗi âm thầm.

## Database Khởi Tạo

Khi app khởi động:

1. Kiểm tra file `data/reddit.db`.
2. Nếu database chưa tồn tại, chạy schema từ:
   ```text
   data/schema_table_reddit.sql
   ```
3. Nếu database đã tồn tại, không tự động drop hoặc recreate.
4. Không dùng `Base.metadata.create_all()` để thay đổi contract ngoài ý muốn nếu schema SQL đang là nguồn chính.
5. Model SQLAlchemy phải khớp chính xác schema hiện tại.

## Yêu Cầu Cho Codex

Khi khởi tạo dự án:

1. Đọc toàn bộ `data/schema_table_reddit.sql` trước khi viết model.
2. Xem database/schema là contract chính.
3. Không tự thêm cột, bảng, enum hoặc migration.
4. Tạo skeleton FastAPI chạy được.
5. Tạo SQLAlchemy model khớp schema.
6. Tạo Pydantic schema cho request/response cần thiết.
7. Tạo repository và service tối thiểu nhưng hoạt động.
8. Implement đủ 4 source type:
   - `subreddit`
   - `keyword`
   - `user`
   - `latest`
9. Implement cookie cache trong file riêng.
10. Implement crawl bài mới trong 24 giờ.
11. Implement update metric đến hạn.
12. Implement crawl comment có kiểm soát bằng `include_comments`.
13. Implement scheduler quét source và post đến hạn.
14. Implement pipeline job và error logging.
15. Viết test cho logic chính.
16. Không thay đổi schema để làm code dễ hơn.
17. Không tạo dữ liệu mẫu giả trong production code.
18. Nếu một thông tin Reddit không có, lưu `NULL` hoặc giá trị mặc định đúng schema; không suy đoán.

## Test

Chạy toàn bộ test:

```bash
pytest
```

Chạy test client riêng:

```bash
pytest tests/test_reddit_client.py
```

Chạy thử app:

```bash
uvicorn app.main:app --reload
```

Kiểm tra health:

```bash
curl http://127.0.0.1:8000/health
```
