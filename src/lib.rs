use std::sync::Arc;

use pyo3::types::PyBytes;
use walle_core::action::Action;
use walle_core::error::WalleResult;
use walle_core::event::Event;
use walle_core::prelude::WalleError;
use walle_core::resp::Resp;
use walle_core::util::{Echo, SelfId};
use walle_core::{ActionHandler, EventHandler, OneBot};

use pyo3::prelude::*;

pub struct Nonebot;

#[async_trait::async_trait]
impl EventHandler<Event, Action, Resp, 12> for Nonebot {
    type Config = ();
    async fn start<AH, EH>(
        &self,
        ob: &Arc<OneBot<AH, EH, 12>>,
        _config: Self::Config,
    ) -> WalleResult<Vec<tokio::task::JoinHandle<()>>>
    where
        AH: ActionHandler<Event, Action, Resp, 12> + Send + Sync + 'static,
        EH: EventHandler<Event, Action, Resp, 12> + Send + Sync + 'static,
    {
        let py_walle = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/py/walle.py"));
        Python::with_gil(|py| -> PyResult<()> {
            PyModule::from_code(py, py_walle, "walle", "walle")?;
            Ok(())
        })
        .map_err(|e| WalleError::Other(e.to_string()))?;
        let ob = ob.clone();
        let join = tokio::spawn(async move {
            let mut sig = ob.get_signal_rx().unwrap();
            while sig.try_recv().is_err() {
                let actionf = || {
                    Python::with_gil(|py| -> PyResult<Option<Vec<u8>>> {
                        py.check_signals()?;
                        let walle = PyModule::import(py, "walle")?;
                        walle
                            .getattr("adapter")?
                            .call_method0("rs_get_action")?
                            .extract()
                    })
                    .unwrap()
                };
                while let Some(action) = actionf() {
                    let ob = ob.clone();
                    tokio::spawn(async move {
                        let action: Echo<Action> = rmp_serde::from_slice(&action).unwrap();
                        let (action, echo_s) = action.unpack();
                        let self_id = action.self_id();
                        let resp = echo_s.pack(ob.action_handler.call(action).await.unwrap());
                        Python::with_gil(|py| -> PyResult<()> {
                            let resp = PyBytes::new(py, &rmp_serde::to_vec(&resp).unwrap());
                            PyModule::import(py, "walle")?
                                .getattr("adapter")?
                                .call_method1("rs_push_resp", (self_id, resp))?;
                            Ok(())
                        })
                        .unwrap();
                    });
                }
                tokio::time::sleep(std::time::Duration::from_millis(500)).await;
            }
        });
        Ok(vec![join])
    }
    async fn call(&self, event: Event) -> WalleResult<()> {
        use walle_core::alt::ColoredAlt;
        if event.ty.as_str() != "meta" {
            tracing::info!("{}", event.colored_alt());
        }
        Python::with_gil(|py| -> PyResult<()> {
            let event = PyBytes::new(py, &rmp_serde::to_vec(&event).unwrap());
            let walle = PyModule::import(py, "walle")?;
            PyModule::import(py, "asyncio")?
                .getattr("run_coroutine_threadsafe")?
                .call1((
                    walle
                        .getattr("adapter")?
                        .call_method1("rs_push_event", (event,))?,
                    walle.getattr("loop")?,
                ))?;
            Ok(())
        })
        .map_err(|e| WalleError::Other(e.to_string()))?;
        Ok(())
    }
    async fn shutdown(&self) {}
}
