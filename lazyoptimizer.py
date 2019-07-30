#! -*- coding: utf-8 -*-

from keras.optimizers import Optimizer
import keras.backend as K


class LazyOptimizer(Optimizer):
    """继承Optimizer类，包装原有优化器，实现Lazy版优化器
    （不局限于LazyAdam，任何带动量的优化器都可以有对应的Lazy版）。
    # 参数
        optimizer：优化器实例，支持目前所有的keras优化器；
        embedding_layers：模型中的Embedding层。
    # 返回
        一个新的keras优化器
    """
    def __init__(self, optimizer, embedding_layers=None, **kwargs):
        super(LazyOptimizer, self).__init__(**kwargs)
        self.optimizer = optimizer
        self.embeddings = []
        if embedding_layers is not None:
            for l in embedding_layers:
                self.embeddings.append(
                    l.trainable_weights[0]
                )
        with K.name_scope(self.__class__.__name__):
            for attr in self.optimizer.get_config():
                if not hasattr(self, attr):
                    value = getattr(self.optimizer, attr)
                    setattr(self, attr, value)
        self.optimizer.get_gradients = self.get_gradients
        self._cache_grads = {}
    def get_gradients(self, loss, params):
        """简单改变一下get_gradients方法，避免重复计算梯度
        """
        _params = []
        for p in params:
            if (loss, p) not in self._cache_grads:
                _params.append(p)
        _grads = super(LazyOptimizer, self).get_gradients(loss, _params)
        for p, g in zip(_params, _grads):
            self._cache_grads[(loss, p)] = g
        return [self._cache_grads[(loss, p)] for p in params]
    def get_updates(self, loss, params):
        # 仅初始化
        self.optimizer.get_updates(loss, params)
        # 常规更新
        dense_params = [p for p in params if p not in self.embeddings]
        self.updates = self.optimizer.get_updates(loss, dense_params)
        # 稀疏更新
        sparse_params = self.embeddings
        sparse_grads = self.get_gradients(loss, sparse_params)
        sparse_flags = [
            K.all(K.not_equal(g, 0), axis=-1, keepdims=True)
            for g in sparse_grads
        ]
        original_lr = self.optimizer.lr
        for f, p in zip(sparse_flags, sparse_params):
            self.optimizer.lr = original_lr * K.cast(f, 'float32')
            self.updates.extend(
                self.optimizer.get_updates(loss, [p])
            )
        self.optimizer.lr = original_lr
        return self.updates
    def get_config(self):
        config = self.optimizer.get_config()
        return config