use std::sync::Arc;

use walle_core::{action::Action, obc::AppOBC, resp::Resp, OneBot};
use walle_nb2::Nonebot;

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();
    let ob = Arc::new(OneBot::new_12(AppOBC::<Action, Resp>::default(), Nonebot));
    let joins = ob
        .start(walle_core::config::AppConfig::default(), (), true)
        .await
        .unwrap();
    for join in joins {
        join.await.ok();
    }
}
